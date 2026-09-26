"""`!compute`: WGSL analysis at build time, the parser, the emitter, and the
agreement between lemur/wgsl.py and the player (assets/svg/compute.js)."""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from lemur import wgsl as W  # noqa: E402

KERNEL = """
//! threads 64
@compute @workgroup_size(64)
fn tick(@builtin(global_invocation_id) id: vec3u) {}
fn mainImage(p: vec2f) -> vec4f { return vec4f(0.0); }
"""


def analyse(src):
    return W.analyse(src)


class LayoutTest(unittest.TestCase):
    """Buffer sizes follow the WGSL memory layout rules."""

    def size(self, decl, extra=""):
        prog = analyse(extra + f"@group(0) @binding(1) var<storage, read_write> x: {decl};\n" + KERNEL)
        return prog.buffers[0].size

    def test_scalars_vectors_arrays(self):
        self.assertEqual(self.size("array<f32, 10>"), 40)
        self.assertEqual(self.size("array<vec2f, 4>"), 32)
        self.assertEqual(self.size("array<vec3f, 4>"), 64)           # vec3 has a 16-byte stride
        self.assertEqual(self.size("array<vec4<f32>, 4>"), 64)
        self.assertEqual(self.size("array<atomic<u32>, 256>"), 1024)
        self.assertEqual(self.size("array<mat3x3f, 2>"), 96)          # 3 columns of 16 bytes

    def test_structs(self):
        s = "struct P { pos: vec2f, vel: vec2f, c: vec3f, m: f32 }\n"
        self.assertEqual(self.size("array<P, 10>", s), 320)           # 32 bytes each
        s = "struct Q { a: f32, b: vec3f }\n"                          # b aligns to 16: size 32
        self.assertEqual(self.size("array<Q, 2>", s), 64)
        s = "struct R { @align(16) a: f32, @size(8) b: f32 }\n"   # 0..4, 4..12, align 16
        self.assertEqual(self.size("array<R, 1>", s), 16)

    def test_const_expressions(self):
        c = "const W = 256u;\nconst H = 128u;\n"
        self.assertEqual(self.size("array<f32, W * H>", c), 4 * 256 * 128)
        self.assertEqual(self.size("array<f32, 1u << 10u>"), 4096)


class AnalysisTest(unittest.TestCase):
    def test_kernels_in_order_with_groups(self):
        prog = analyse("""
const N = 1000u;
@group(0) @binding(1) var<storage, read_write> a: array<f32, N>;
//! threads N
//! once
@compute @workgroup_size(64)
fn init(@builtin(global_invocation_id) id: vec3u) {}
//! threads 512 300
@compute @workgroup_size(16, 16)
fn step(@builtin(global_invocation_id) id: vec3u) {}
fn mainImage(p: vec2f) -> vec4f { return vec4f(0.0); }
""")
        (init, step) = prog.kernels
        self.assertEqual((init.name, init.once, init.groups), ("init", True, (16, 1, 1)))
        self.assertEqual((step.name, step.once, step.groups), ("step", False, (32, 19, 1)))

    def test_errors_carry_lines(self):
        cases = {
            "array<f32>": "fixed length",
            "array<f32, 4>;\n@group(0) @binding(1) var<storage> y: array<f32, 4>": "already used",
        }
        for decl, msg in cases.items():
            with self.assertRaisesRegex(W.WGSLError, msg):
                analyse(f"@group(0) @binding(1) var<storage, read_write> x: {decl};\n" + KERNEL)
        with self.assertRaisesRegex(W.WGSLError, "binding 0"):
            analyse("@group(0) @binding(0) var<storage> x: array<f32, 4>;\n" + KERNEL)
        with self.assertRaisesRegex(W.WGSLError, "only uniform"):
            analyse("@group(0) @binding(1) var<uniform> u: vec4f;\n" + KERNEL)
        with self.assertRaisesRegex(W.WGSLError, "threads N"):
            analyse("@compute @workgroup_size(64)\nfn k() {}\nfn mainImage(p: vec2f) -> vec4f { return vec4f(0.0); }")
        with self.assertRaisesRegex(W.WGSLError, "mainImage"):
            analyse("//! threads 4\n@compute @workgroup_size(4)\nfn k() {}\n")
        with self.assertRaisesRegex(W.WGSLError, "unknown annotation"):
            analyse("//! thread 4\n@compute @workgroup_size(4)\nfn k() {}\n" + KERNEL)
        try:
            analyse("\n\n@group(0) @binding(1) var<storage, read_write> x: array<f32>;\n" + KERNEL)
        except W.WGSLError as exc:
            self.assertEqual(exc.line, 3)

    def test_comments_and_workgroup_vars_are_ignored(self):
        prog = analyse("""
// @group(0) @binding(1) var<storage, read_write> ghost: array<f32>;
/* var<storage> nope: array<f32>; */
var<workgroup> tile: array<f32, 64>;
@group(0) @binding(2) var<storage, read> real: array<u32, 8>;
""" + KERNEL)
        self.assertEqual([(b.name, b.access, b.size) for b in prog.buffers], [("real", "read", 32)])

    def test_includes_map_lines(self):
        tmp = tempfile.mkdtemp(prefix="lemur-wgsl-")
        self.addCleanup(shutil.rmtree, tmp, True)
        with open(os.path.join(tmp, "lib.wgsl"), "w") as fh:
            fh.write("fn helper() -> f32 { return 1.0; }\nfn other() -> f32 { return 2.0; }\n")
        with open(os.path.join(tmp, "main.wgsl"), "w") as fh:
            fh.write('#include "lib.wgsl"\n' + KERNEL)
        text, lines = W.read_source(os.path.join(tmp, "main.wgsl"))
        self.assertNotIn("#include", text)
        self.assertEqual(os.path.basename(lines[1][0]), "lib.wgsl")
        self.assertEqual((os.path.basename(lines[2][0]), lines[2][1]), ("main.wgsl", 2))
        man = W.analyse(text, lines).manifest()
        self.assertEqual(man["files"], ["lib.wgsl", "main.wgsl"])
        self.assertEqual(man["lines"][0], [0, 1, 2])


class ParserTest(unittest.TestCase):
    def ast(self, text):
        from lemur.parser import Parser, deck_to_ast
        from lemur.parser import Line
        lines = [Line("t.lmr", i + 1, ln) for i, ln in enumerate(text.split("\n"))]
        return deck_to_ast(Parser(lines).parse())

    def test_directives(self):
        ast = self.ast("!slide A\n\n!compute Flow ^f\n\t!src f.wgsl\n\t!steps slide\n\t!rate 120\n"
                       "\t!seed 7\n\t!warmup 1.5\n\t!viewport full\n")
        node = next(b for b in ast["body"] if b["type"] == "compute")
        self.assertEqual({k: node[k] for k in ("src", "steps", "rate", "seed", "warmup", "viewport")},
                         {"src": "f.wgsl", "steps": "slide", "rate": 120.0, "seed": 7, "warmup": 1.5,
                          "viewport": "full"})
        self.assertEqual(node["id"], "f")

    def test_bad_directives(self):
        from lemur.parser import LemurError
        for bad in ("\t!steps many\n", "\t!rate 0\n", "\t!seed -1\n"):
            with self.assertRaises(LemurError):
                self.ast("!slide A\n\n!compute\n\t!src f.wgsl\n" + bad)
        with self.assertRaises(LemurError):
            self.ast("!slide A\n\n!compute\n\t!steps 2\n")


try:
    from lemur.emit import svg as _svg                                   # noqa: F401
    _HAVE_SVG = True
except Exception:                                                       # pragma: no cover
    _HAVE_SVG = False


@unittest.skipUnless(_HAVE_SVG, "needs the svg emitter")
class EmitTest(unittest.TestCase):
    def build(self, deck, files):
        from lemur.emit import svg
        tmp = tempfile.mkdtemp(prefix="lemur-compute-")
        self.addCleanup(shutil.rmtree, tmp, True)
        for name, text in files.items():
            with open(os.path.join(tmp, name), "w", encoding="utf-8") as fh:
                fh.write(text)
        with open(os.path.join(tmp, "deck.lmr"), "w", encoding="utf-8") as fh:
            fh.write(deck)
        html = svg.build_html(os.path.join(tmp, "deck.lmr"))[0]
        return html, list(svg.LAST_WARNINGS)

    def test_manifest_and_player(self):
        wgsl = "@group(0) @binding(1) var<storage, read_write> a: array<f32, 64>;\n" + KERNEL
        html, warns = self.build("!slide A\n\n!compute\n\t!src k.wgsl\n\t!steps slide\n", {"k.wgsl": wgsl})
        self.assertEqual(warns, [])
        man = json.loads(re.search(r'data-manifest="([^"]+)"', html).group(1).replace("&quot;", '"'))
        self.assertEqual(man["buffers"], [{"name": "a", "binding": 1, "size": 256, "access": "read_write"}])
        self.assertEqual(man["kernels"], [{"name": "tick", "groups": [1, 1, 1], "once": False}])
        self.assertIn('data-steps="slide"', html)
        self.assertIn("lmr-compute-box", html)
        self.assertIn("navigator.gpu", html)                              # the WebGPU player shipped

    def test_no_player_without_compute(self):
        html, _ = self.build("!slide A\n\ntext\n", {})
        self.assertNotIn("navigator.gpu", html)

    def test_wgsl_error_is_reported_with_its_line(self):
        wgsl = "\n@group(0) @binding(1) var<storage, read_write> a: array<f32>;\n" + KERNEL
        html, warns = self.build("!slide A\n\n!compute\n\t!src k.wgsl\n", {"k.wgsl": wgsl})
        self.assertTrue(any("k.wgsl:2" in w and "fixed length" in w for w in warns), warns)
        self.assertIn("lmr-shader-error", html)
        self.assertNotIn("navigator.gpu", html)


class TwinTest(unittest.TestCase):
    """The prelude and tail the player adds are the ones wgsl.py documents."""

    def test_prelude_and_tail_agree(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("node not installed")
        js = (ROOT / "lemur/assets/svg/compute.js").read_text()
        decl = re.search(r"var PRELUDE = .*?;\n  var PRELUDE_LINES", js, re.S).group(0).rsplit("\n", 1)[0]
        tail = re.search(r"var TAIL = .*?;\n", js, re.S).group(0)
        out = subprocess.run([node, "-e", decl + "\n" + tail + "\nconsole.log(JSON.stringify([PRELUDE, TAIL]));"],
                             capture_output=True, text=True, check=True).stdout
        prelude, tail_s = json.loads(out)
        self.assertEqual(prelude, W.PRELUDE)
        self.assertEqual(tail_s, W.TAIL)


if __name__ == "__main__":
    unittest.main()
