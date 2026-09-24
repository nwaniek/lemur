"""The lifted animation stack (lemur.anim): an ``Anim`` produces the keyframe IR
the emitter bakes. Needs numpy (the svg extra) but not the full Pango/LaTeX
toolchain for shapes without text."""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

try:
    import numpy  # noqa: F401
    from lemur.anim import Anim, Circle, Create, RIGHT  # noqa: F401
    _HAVE = True
except Exception:
    _HAVE = False


@unittest.skipUnless(_HAVE, "needs numpy (the svg extra)")
class AnimIRTest(unittest.TestCase):
    def test_circle_produces_keyframe_ir(self):
        from lemur.anim import Anim, Circle, Create, RIGHT

        class Spike(Anim):
            def build(self):
                c = Circle(radius=1.0)
                self.play(Create(c))          # beat 0->1: draw on
                self.next()
                self.play(c.animate.shift(RIGHT * 2))  # beat 1->2: translate
                self.next()

        data = Spike().render()
        self.assertGreaterEqual(set(data), {"nodes", "tracks", "beats", "camera", "duration"})
        self.assertEqual([b["t"] for b in data["beats"]], [1.0, 2.0])   # two beats = two steps
        self.assertEqual(len(data["nodes"]), 1)                          # one circle
        self.assertEqual(data["nodes"][0]["k"], "path")                  # baked outline
        props = {tr["p"] for tr in data["tracks"]}
        self.assertIn("t", props)    # a transform track (6-number affine)
        self.assertIn("dr", props)   # a draw-range track (Create -> stroke-dasharray)
        # the translate track ends at x=+2 (world units)
        moves = [tr for tr in data["tracks"] if tr["p"] == "t" and tr["t0"] == 1.0]
        self.assertTrue(moves and abs(moves[0]["v"][-1][4] - 2.0) < 1e-6)

    def test_shape_is_the_renamed_base(self):
        # the manim-isms were renamed: Shape/VShape (not Mobject), Anim (not Scene)
        import lemur.anim as A
        self.assertTrue(hasattr(A, "Shape") and hasattr(A, "VShape") and hasattr(A, "Anim"))
        self.assertFalse(hasattr(A, "Mobject") or hasattr(A, "Scene"))


@unittest.skipUnless(_HAVE, "needs numpy (the svg extra)")
class ViewTest(unittest.TestCase):
    """Build-time 3D: an orthographic projection whose orbit bakes into morphs."""

    def test_projection_orthographic(self):
        import numpy as np
        from lemur.anim import View

        # elev=90 looks straight down z: (x, y) survive, z is ignored.
        top = View(azim=0, elev=90, scale=1.0)
        np.testing.assert_allclose(top.project([2.0, 3.0, 9.0]), [2.0, 3.0], atol=1e-9)
        # elev=0 looks edge-on: z becomes the vertical screen axis.
        side = View(azim=0, elev=0, scale=1.0)
        np.testing.assert_allclose(side.project([2.0, 3.0, 5.0]), [2.0, 5.0], atol=1e-9)
        # a viewport centres the projection at its rect centre.
        inset = View(azim=0, elev=90, scale=1.0, viewport=(2.0, -1.0, 6.0, 6.0))
        np.testing.assert_allclose(inset.project([1.0, 3.0, 9.0]), [3.0, 2.0], atol=1e-9)

    def test_camera_orbit_bakes_a_morph(self):
        import numpy as np
        from lemur.anim import Anim, Create, View

        class Orbit(Anim):
            def build(self):
                sp = View(elev=90)
                helix = sp.parametric(lambda t: (np.cos(t), np.sin(t), t),
                                      0.0, 6.28, samples=40)
                self.play(Create(helix))
                self.next()
                self.play(*sp.reorient(elev=20), run_time=1.0)   # tilt the view
                self.next()

        data = Orbit().render()
        # the curve ships once in 3-D; tilting the camera is one small angle track
        # that the player projects with — no per-frame 2-D morph
        self.assertFalse(any(tr["p"] == "d" for tr in data["tracks"]))
        (node,) = [n for n in data["nodes"] if n.get("k") == "w"]
        self.assertEqual(len(node["s"]["p3"]), 3 * 40)
        (view,) = data["views"]
        self.assertTrue(view["ae"])
        self.assertEqual([b["t"] for b in data["beats"]], [1.0, 2.0])

    def test_surface_and_synced_trace_dot(self):
        import numpy as np
        from lemur.anim import Anim, Create, View, ValueTracker

        class Scene(Anim):
            def build(self):
                sp = View(elev=55, scale=0.9)
                surf = sp.surface(lambda u, v: (u, v, 0.0), (-1, 1), (-1, 1),
                                  u_lines=5, v_lines=5, samples=8)
                prog = ValueTracker(0.0)
                dot = sp.trace_dot([[0, 0, 0], [1, 0, 0], [1, 1, 0]], prog)
                self.add(surf, dot)
                self.play(Create(surf), prog.animate.set_value(1.0), run_time=1.0)
                self.next()

        data = Scene().render()
        self.assertGreaterEqual(len(data["nodes"]), 11)                    # 5+5 wires + a dot
        self.assertTrue(any(tr["p"] == "a3" for tr in data["tracks"]))     # the dot moves (in 3-D)

    def test_clip_region_and_index_rate(self):
        from lemur.anim import Anim, Create, View, ValueTracker

        self.assertTrue(callable(View().rate([[0, 0, 0], [1, 1, 1]])))   # a Create rate_func

        class Clipped(Anim):
            def build(self):
                v = View(azim=0, elev=6, scale=0.5, viewport=(4, 0, 3, 2))
                pts = [[-2, 0, -1], [0, 0, 0], [2, 0, 1]]
                prog = ValueTracker(0.0)
                self.add(v.trace_dot(pts, prog, by="index"))
                self.play(Create(v.curve(pts), rate_func=v.rate(pts)),
                          prog.animate(rate_func="linear").set_value(1.0), run_time=1)
                self.next()

        data = Clipped().render()
        clips = [n["clip"] for n in data["nodes"] if "clip" in n]
        # shapes made through the view carry the panel region (cx-w/2, cy-h/2, w, h)
        self.assertTrue(clips and clips[0] == [2.5, -1.0, 3.0, 2.0])

    def test_perspective_and_solid_box(self):
        import numpy as np
        from lemur.anim import Anim, FadeIn, View

        v = View(azim=0, elev=30, scale=1.0, perspective=5.0)   # camera above, looking down
        high = float(np.hypot(*v.project([1.0, 0.0, 2.0])))     # higher z is nearer …
        low = float(np.hypot(*v.project([1.0, 0.0, -2.0])))
        self.assertGreater(high, low)                           # … so perspective magnifies it

        class Box(Anim):
            def build(self):
                self.play(FadeIn(v.box((0, 0, 0), 1.0, fill_opacity=0.9)))
                self.next()

        data = Box().render()
        faces = [n for n in data["nodes"] if n["k"] == "w"]
        self.assertEqual(len(faces), 6)                          # a cube's 6 faces, projected by the player
        self.assertEqual(data["views"][0]["p"], 5.0)


class WorldShapeTest(unittest.TestCase):
    """3-D shapes ship world geometry; the still frame is projected at build time."""

    def _scene(self):
        import numpy as np
        from lemur.anim import Anim, Create, FadeIn, View, ValueTracker

        class Scene(Anim):
            def build(self):
                v = View(azim=0, elev=20, scale=1.0)
                v.occluder = {"c": [0.0, 0.0, 0.0], "R": 1.0, "cap": None}
                k = ValueTracker(3.0)
                # a curve whose point count changes as it grows, split by the occluder
                arc = v.curve_fn(lambda: [(1.01 * np.cos(t), 1.01 * np.sin(t), 0.0)
                                          for t in np.linspace(0, np.pi, int(k.get_value()))],
                                 rule="vis", color="#123456", stroke_width=3)
                front = v.dot((0.0, -1.0, 0.0), rule="hide")      # faces the camera
                back = v.dot((0.0, 1.0, 0.0), rule="hide")        # behind the sphere
                self.play(Create(arc), FadeIn(front), FadeIn(back))
                self.play(k.animate.set_value(40.0), run_time=1.0)
                self.play(*v.reorient(azim=180), run_time=1.0)    # now the other dot is in front
                self.next()

        return Scene().render()

    def test_ir_carries_world_specs(self):
        data = self._scene()
        polys = [n for n in data["nodes"] if n.get("k") == "w"]
        self.assertEqual(len(polys), 1)
        self.assertEqual(polys[0]["wr"], "vis")
        self.assertEqual(polys[0]["struct"][0], [40])        # one layout for every keyframe
        anchors = [n for n in data["nodes"] if n.get("wk") == "anchor"]
        self.assertEqual({n["wr"] for n in anchors}, {"hide"})
        (view,) = data["views"]
        self.assertEqual(view["occ"]["R"], 1.0)
        self.assertAlmostEqual(view["ae"][-1]["v"][-1][0], 3.14159, places=4)

class WorldTwinTest(unittest.TestCase):
    """lemur.anim.world (the still frame) and the runtime's LMRW (every frame)
    must draw the same thing."""

    def test_python_and_js_projection_agree(self):
        import json
        import shutil
        import subprocess
        from pathlib import Path

        import numpy as np
        from lemur.anim import world as W

        node = shutil.which("node")
        if not node:
            self.skipTest("node not installed")
        js = (Path(__file__).resolve().parents[2] / "lemur/assets/svg/world.js").read_text()
        rng = np.random.default_rng(3)
        cases = []
        for k in range(12):
            occ = {"c": [0.1, -0.2, 0.0], "R": 1.0, "cap": 0.0 if k % 2 else None}
            cam = W.Camera(float(rng.uniform(-3, 3)), float(rng.uniform(0.1, 1.4)), 1.7, (0.3, -0.2),
                           (0.0, 0.0, 0.0), 6.0 if k % 3 == 0 else None)
            t = np.linspace(0, 2 * np.pi, 41)[:-1]
            ring = np.stack([1.02 * np.cos(t), 1.02 * np.sin(t) * np.cos(k), 1.02 * np.sin(t) * np.sin(k)], 1) + occ["c"]
            arc = rng.normal(size=(25, 3)) * 0.8
            polys, closed = [ring, arc], [True, False]
            for kind, rule in [("poly", None), ("poly", "vis"), ("poly", "hid"), ("limb", None), ("base", None)]:
                if kind == "base" and occ["cap"] is None:
                    continue
                py = [[np.round(P, 6).tolist(), cl] for P, cl in W.bake_paths(kind, rule, occ, cam, polys, closed)]
                cases.append({"kind": kind, "rule": rule, "occ": occ, "py": py,
                              "cam": {"a": cam.azim, "e": cam.elev, "s": cam.scale, "c": cam.center,
                                      "o": cam.origin, "p": cam.persp},
                              "P": np.concatenate(polys).ravel().tolist(), "struct": [[len(P) for P in polys], [1, 0]]})
        script = ("var window = {};\n" + js + "\nvar LMRW = window.LMRW;\n" +
                  "var cases = JSON.parse(require('fs').readFileSync(0, 'utf8'));\n"
                  "console.log(JSON.stringify(cases.map(function (c) {"
                  " return LMRW.paths(c.kind, c.rule, c.occ, c.cam, c.P, c.struct); })));")
        out = subprocess.run([node, "-e", script], input=json.dumps(cases), capture_output=True, text=True, check=True)
        for case, got in zip(cases, json.loads(out.stdout)):
            self.assertEqual(len(got), len(case["py"]), (case["kind"], case["rule"]))
            for (gp, gc), (pp, pc) in zip(got, case["py"]):
                self.assertEqual(bool(gc), bool(pc))
                np.testing.assert_allclose(np.asarray(gp), np.asarray(pp), atol=1e-5)
        self.assertTrue(any(c["rule"] == "hid" and c["py"] for c in cases))   # the split was exercised


if __name__ == "__main__":
    unittest.main()
