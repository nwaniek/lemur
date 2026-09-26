"""GPU views (View(renderer="gpu")): mesh geometry, its twin in the player
(assets/svg/world.js), the animation IR, and the vector still the emitter bakes
for print and PDF."""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from lemur.anim import world as W  # noqa: E402


def torus(R=2.0, r=0.7, nu=40, nv=20):
    us = np.linspace(0, 2 * np.pi, nu + 1)
    vs = np.linspace(0, 2 * np.pi, nv + 1)
    P = np.array([[(R + r * np.cos(v)) * np.cos(u), (R + r * np.cos(v)) * np.sin(u), r * np.sin(v)]
                  for u in us for v in vs])
    idx = lambda i, j: i * (nv + 1) + j                                       # noqa: E731
    faces = np.array([[idx(i, j), idx(i + 1, j), idx(i + 1, j + 1), idx(i, j + 1)]
                      for i in range(nu) for j in range(nv)])
    return P, faces


class MeshGeometryTest(unittest.TestCase):
    def setUp(self):
        self.P, self.faces = torus()
        self.geo = W.mesh_geo(self.P, self.faces)
        self.cam = W.Camera(np.radians(-30), np.radians(25), 1.0, (0.0, 0.0), (0.0, 0.0, 0.0), None)

    def test_seams_weld_into_a_closed_surface(self):
        self.assertEqual(self.geo.ids.max() + 1, 40 * 20)
        self.assertEqual(len(self.geo.boundary), 0)
        self.assertEqual(len(self.geo.tris), 2 * 40 * 20)

    def test_the_torus_hides_its_underside_not_its_top(self):
        occ = {"meshes": [W.mesh_occluder(self.P, self.geo)]}
        u = np.linspace(0, 2 * np.pi, 8, endpoint=False)
        top = np.stack([2 * np.cos(u), 2 * np.sin(u), np.full(8, 0.7)], 1)
        bottom = np.stack([2 * np.cos(u), 2 * np.sin(u), np.full(8, -0.7)], 1)
        self.assertFalse(W.occluded_many(occ, self.cam, top).any())
        self.assertTrue(W.occluded_many(occ, self.cam, bottom).all())

    def test_contour_is_two_smooth_loops(self):
        loops = W.contour(self.cam, self.P, self.geo)
        self.assertEqual(len(loops), 2)                          # the outer rim and the hole
        for L in loops:
            self.assertTrue(np.allclose(L[0], L[-1]))             # closed

    def test_painter_culls_and_sorts_far_to_near(self):
        faces = W.painter_faces(self.cam, self.P, self.geo, cull=True)
        self.assertLess(len(faces), len(self.faces))
        d = [W.depth(self.cam, self.P[self.faces[i]].mean(axis=0)) for i, _ in faces]
        self.assertEqual(d, sorted(d))

    def test_open_boundary_is_an_outline(self):
        P, faces = torus(nv=10)
        half = faces[: len(faces) // 2]                           # half a torus: an open surface
        geo = W.mesh_geo(P, half)
        self.assertGreater(len(geo.boundary), 0)


class TwinTest(unittest.TestCase):
    """The player's mesh maths (world.js) agrees with world.py."""

    def test_occlusion_contour_and_painter_agree(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("node not installed")
        P, faces = torus()
        geo = W.mesh_geo(P, faces)
        Q = np.random.default_rng(1).uniform(-3, 3, (200, 3))
        cases = []
        for a, e, p in [(-0.5, 0.45, None), (2.1, -0.3, None), (0.7, 0.9, 7.0)]:
            cam = W.Camera(a, e, 1.3, (0.2, -0.1), (0.0, 0.0, 0.1), p)
            occ = {"meshes": [W.mesh_occluder(P, geo)]}
            cont = W.contour(cam, P, geo)
            cases.append({"cam": {"a": a, "e": e, "s": 1.3, "c": [0.2, -0.1], "o": [0, 0, 0.1], "p": p},
                          "flags": W.occluded_many(occ, cam, Q).tolist(),
                          "npts": sum(len(c) for c in cont), "nlines": len(cont),
                          "order": [i for i, _ in W.painter_faces(cam, P, geo, True)]})
        js = (ROOT / "lemur/assets/svg/world.js").read_text()
        script = ("var window = {};\n" + js + "\nvar L = window.LMRW;\n"
                  "var d = JSON.parse(require('fs').readFileSync(0, 'utf8'));\n"
                  "var geo = L.meshGeo(d.P, d.faces, 4);\n"
                  "console.log(JSON.stringify(d.cases.map(function (cs) {\n"
                  "  var occ = { meshes: [L.meshOccluder(d.P, geo)] }, cont = L.contour(cs.cam, d.P, geo);\n"
                  "  return { flags: d.Q.map(function (q) { return L.occludes(occ, cs.cam, q[0], q[1], q[2]); }),\n"
                  "           npts: cont.reduce(function (s, c) { return s + c.length; }, 0), nlines: cont.length,\n"
                  "           order: L.painterFaces(cs.cam, d.P, geo, true).map(function (f) { return f[0]; }) };\n"
                  "})));")
        out = subprocess.run([node, "-e", script], capture_output=True, text=True, check=True,
                             input=json.dumps({"P": P.ravel().tolist(), "faces": faces.ravel().tolist(),
                                               "Q": Q.tolist(), "cases": cases}))
        for py, js_ in zip(cases, json.loads(out.stdout)):
            self.assertEqual(py["flags"], js_["flags"])
            self.assertEqual((py["npts"], py["nlines"]), (js_["npts"], js_["nlines"]))
            self.assertEqual(py["order"], js_["order"])


ANIM = '''
import numpy as np
from lemur.anim import Anim, View, Create, FadeIn
from lemur.anim.illustrate import Figure, Torus

class T(Anim):
    def build(self):
        fig = Figure(View(azim=-30, elev=28, scale=1.2, renderer="gpu"), Torus(2.0, 0.75))
        shadow, solid, outline = fig.backdrop(nu=32)
        knot = [fig.occ.surface(2 * s, 3 * s) for s in np.linspace(0, 2 * np.pi, 120)]
        curve = fig.curve(lambda: knot, closed=True)
        self.play(FadeIn(solid), FadeIn(shadow), Create(outline))
        self.play(*[Create(m) for m in curve])
        self.next()
        self.play(*fig.view.reorient(azim=100, elev=-15), run_time=2)
        self.next()
'''


class IRTest(unittest.TestCase):
    def render(self):
        tmp = tempfile.mkdtemp(prefix="lemur-gpu-")
        self.addCleanup(shutil.rmtree, tmp, True)
        with open(os.path.join(tmp, "t.py"), "w") as fh:
            fh.write(ANIM)
        sys.path.insert(0, tmp)
        try:
            import importlib
            mod = importlib.import_module("t")
            return mod.T().render()
        finally:
            sys.path.remove(tmp)
            sys.modules.pop("t", None)

    def test_mesh_contour_and_gpu_view(self):
        data = self.render()
        (view,) = data["views"]
        self.assertEqual(view.get("gpu"), 1)
        self.assertIsNone(view.get("occ"))                    # a torus: the meshes are the occluder
        meshes = [n for n in data["nodes"] if n.get("wk") == "mesh"]
        solid = next(n for n in meshes if n.get("occ"))
        self.assertEqual(solid["fsz"], 4)
        self.assertEqual(len(solid["faces"]), 4 * 32 * 32)
        self.assertEqual(len(solid["fcs"]), 3 * 32 * 32)
        self.assertEqual(len(solid["s"]["p3"]), 3 * 33 * 33)   # static: stored once
        (cont,) = [n for n in data["nodes"] if n.get("wk") == "contour"]
        self.assertEqual(cont["src"], solid["i"])
        self.assertTrue(any(n.get("wr") == "hid" for n in data["nodes"]))


try:
    from lemur.emit import svg as _svg                                   # noqa: F401
    _HAVE_SVG = True
except Exception:                                                       # pragma: no cover
    _HAVE_SVG = False


@unittest.skipUnless(_HAVE_SVG, "needs the svg emitter")
class EmitTest(unittest.TestCase):
    def build(self, deck, files):
        from lemur.emit import svg
        tmp = tempfile.mkdtemp(prefix="lemur-gpu-")
        self.addCleanup(shutil.rmtree, tmp, True)
        for name, text in files.items():
            with open(os.path.join(tmp, name), "w", encoding="utf-8") as fh:
                fh.write(text)
        with open(os.path.join(tmp, "deck.lmr"), "w", encoding="utf-8") as fh:
            fh.write(deck)
        return svg.build_html(os.path.join(tmp, "deck.lmr"))[0]

    def test_vector_still_canvas_layer_and_renderer(self):
        html = self.build("!slide A\n\n!anim\n\t!src t.py\n", {"t.py": ANIM})
        still = re.search(r'<g class="lmr-gv" data-gv="0"[^>]*>(.*?)</g>', html, re.S).group(1)
        self.assertGreater(still.count("<path"), 300)                  # painter-sorted faces …
        self.assertIn("stroke-dasharray", still)                        # … and the dashed hidden line
        self.assertIn('class="lmr-gl"', html)                           # the canvas sits in the layers
        self.assertEqual(html.count('class="anim-cam"'), 2)             # below | canvas | above
        self.assertIn("window.LMRGL = {", html)                         # the WebGL renderer shipped
        self.assertIn(".lmr-gl { display: none !important; }", html)    # print shows the still

    def test_no_renderer_without_gpu_views(self):
        html = self.build("!slide A\n\ntext\n", {})
        self.assertNotIn("window.LMRGL = {", html)


class FigureTest(unittest.TestCase):
    def test_torus_needs_a_gpu_view(self):
        from lemur.anim import View
        from lemur.anim.illustrate import Figure, Torus
        with self.assertRaises(ValueError):
            Figure(View(), Torus())
        fig = Figure(View(renderer="gpu"), Torus())
        with self.assertRaises(ValueError):
            fig.silhouette()                                            # needs the solid first
        _s, solid, outline = fig.backdrop(nu=16)
        self.assertEqual(outline.submobjects[0].world.kind, "contour")
        self.assertTrue(fig.hidden([2.0, 0.0, -0.75]))
        self.assertFalse(fig.hidden([2.0, 0.0, 0.75]))


if __name__ == "__main__":
    unittest.main()
