"""Parity/hardening tests for the SVG emitter against the HTML deck's behaviour.

Each test pins a construct that the build-time SVG path once dropped or laid out
differently from the HTML deck (inline reveals, nested lists, overlay specs,
CSS themes, TeX boxes, whitespace, …). Geometry is introspected through named
marks (``[text]^name``), whose boxes the emitter records while placing glyphs.
Toolchain-gated like test_svg_emit.
"""

import os
import shutil
import sys
import tempfile
import textwrap
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from lemur.emit import svg  # noqa: E402
from lemur.layout import steps  # noqa: E402
from lemur.layout.inline import TextStyle, layout_block  # noqa: E402
from lemur.typeset import latex, pango  # noqa: E402

_TOOLCHAIN = (pango.available() and shutil.which("latex") is not None
              and shutil.which("dvisvgm") is not None)


class StepGateTest(unittest.TestCase):
    """The reveal-spec grammar: n, n-, -n, n-m and comma lists (stdlib only)."""

    def test_forms(self):
        self.assertEqual(steps.parse_spec("2-"), ((2, None),))
        self.assertEqual(steps.parse_spec("3"), ((3, 3),))
        self.assertEqual(steps.parse_spec("-3"), ((0, 3),))
        self.assertEqual(steps.parse_spec("2-4"), ((2, 4),))
        self.assertEqual(steps.parse_spec("1,3-4,6-"), ((1, 1), (3, 4), (6, None)))

    def test_merge_and_garbage(self):
        self.assertEqual(steps.parse_spec("1-2,3"), ((1, 3),))
        self.assertEqual(steps.parse_spec("x"), steps.ALWAYS)   # never silently hide content

    def test_combine(self):
        self.assertEqual(steps.combine(((1, None),), ((0, 3),)), ((1, 3),))
        self.assertEqual(steps.combine(((1, 1), (4, None)), ((2, None),)), ((4, None),))
        self.assertEqual(steps.combine(((1, 1),), ((3, None),)), steps.NEVER)

    def test_max_step_counts_bounds(self):
        # a slide needs as many steps as the largest number used on it
        self.assertEqual(steps.max_step(steps.parse_spec("-3")), 3)
        self.assertEqual(steps.max_step(steps.parse_spec("1,5")), 5)


@unittest.skipUnless(_TOOLCHAIN, "needs Pango (PyGObject) and latex+dvisvgm")
class SvgParityTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="lemur-parity-")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def build(self, src: str, files: "dict | None" = None) -> str:
        for rel, text in (files or {}).items():
            p = os.path.join(self.tmp, rel)
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, "w", encoding="utf-8") as fh:
                fh.write(textwrap.dedent(text))
        path = os.path.join(self.tmp, "deck.lmr")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(textwrap.dedent(src))
        html, _ = svg.build_html(path)
        return html

    def slides(self, src: str) -> list:
        """Render ``src`` and return each slide's ``Slide`` object (for marks)."""
        captured = []
        orig = svg._TEMPLATES["content"]

        def spy(ctx):
            orig(ctx)
            captured.append(ctx.slide)

        svg._TEMPLATES["content"] = spy
        try:
            self.build(src)
        finally:
            svg._TEMPLATES["content"] = orig
        return captured

    # -- reveals ------------------------------------------------------------

    def test_inline_span_reveal_is_gated(self):
        html = self.build("!slide A\n\nshown [later]<2-> and [then]<+-> too\n")
        self.assertRegex(html, r'data-step="2"')
        self.assertRegex(html, r'data-step="1"')     # `<+->` takes the next auto step

    def test_comma_spec_uses_step_list(self):
        html = self.build("!slide A\n\n!when<1,3>\n\tonly on one and three\n")
        self.assertIn('data-steps="1-1,3-3"', html)

    def test_bounded_spec_is_final_hidden(self):
        # a layer gone by the last step is marked for print/overview
        html = self.build("!slide A\n\n!stack\n\t!layer<1>\n\t\tfirst\n\t!layer<2->\n\t\tsecond\n")
        self.assertIn('data-step="1" data-until="1" data-final="0"', html)

    def test_mark_reveal_gates_connector(self):
        sl = self.slides("!slide A\n\n[a]^p and [b]^q<2->\n\n!connect\n\tp -> q\n")[0]
        self.assertEqual(sl.mark_gate("q"), ((2, None),))

    # -- structure ------------------------------------------------------------

    def test_nested_list_is_rendered_and_indented(self):
        sl = self.slides("!slide A\n\n- [top]^t\n\t- [nested]^n\n")[0]
        (t,), (n,) = sl.mark_boxes("t"), sl.mark_boxes("n")
        self.assertGreater(n[0], t[0] + 40)       # one list level deeper
        self.assertGreater(n[1], t[3])            # on the next line

    def test_connect_inside_environment_is_drawn(self):
        html = self.build("!slide A\n\n!theorem T\n\t[a]^p then [b]^q\n\n\t!connect\n\t\tp -> q\n")
        self.assertIn('stroke-width="3.5"', html)

    def test_emphasis_only_annotation_keeps_colour_and_is_bold(self):
        html = self.build("!slide A\n\nthe [key]^k word\n\n!annotate\n\tk[.bold]:\n")
        self.assertIn('stroke-width="0.035"', html)   # the bold copy
        self.assertNotIn('fill="#c05d28"', html)       # no palette colour was forced

    def test_title_keeps_inline_maths(self):
        sl = self.slides("!slide Title with $\\mk{x}{x^2}$ maths\n\nbody\n")[0]
        self.assertTrue(sl.mark_boxes("x"))

    def test_body_starts_below_a_wrapped_title(self):
        long = "A very long slide title " * 6
        one = self.slides("!slide Short\n\n[body]^b\n")[0].mark_boxes("b")[0]
        two = self.slides(f"!slide {long}\n\n[body]^b\n")[0].mark_boxes("b")[0]
        self.assertGreater(two[1], one[1] + 40)

    # -- themes ---------------------------------------------------------------

    def test_deck_local_css_theme(self):
        css = ":root { --lmr-bg: #fafaf0; --lmr-font-size: 37px; --lmr-accent: #123456; }\n"
        html = self.build("!theme mine\n!title T\n\n!slide A\n\ntext\n",
                          files={"themes/mine/theme.css": css})
        self.assertIn("--bg:#fafaf0", html)
        self.assertIn("--accent:#123456", html)

    def test_unknown_theme_warns(self):
        self.build("!theme nosuchtheme\n\n!slide A\n\ntext\n")
        self.assertTrue(any("nosuchtheme" in w for w in svg.LAST_WARNINGS))

    # -- maths ----------------------------------------------------------------

    def test_unicode_maths(self):
        self.build("!slide A\n\nlanguage $𝐿 = \\{10^*1\\}$ and $r ≥ 0$\n")

    def test_display_environment_in_block(self):
        self.build("!slide A\n\n:: math\n\t\\begin{align}\n\t a &= b \\\\\n\t c &= d\n\t\\end{align}\n")

    def test_latex_error_is_soft(self):
        html = self.build("!slide A\n\nbroken $\\frac{1}{$ here\n")
        self.assertIn("<svg", html)
        self.assertTrue(any("LaTeX error" in w for w in svg.LAST_WARNINGS))

    def test_tex_box_keeps_spacing(self):
        _, plain = latex.tex_render(latex.wrap("x", "inline"))
        _, spaced = latex.tex_render(latex.wrap("\\qquad x", "inline"))
        self.assertGreater(spaced.width, plain.width + 1.5)   # \qquad = 2em

    def test_wrap_rewrites_display_environments(self):
        self.assertNotIn("{align}", latex.wrap("\\begin{align} a &= b \\end{align}", "display"))
        self.assertIn("gathered", latex.wrap("a \\\\ b", "display"))
        self.assertNotIn("aligned", latex.wrap("\\begin{pmatrix}a&b\\end{pmatrix}", "display"))

    # -- references -------------------------------------------------------------

    def test_unresolved_reference_warns(self):
        self.build("!slide A\n\nsee @nowhere and @(nokey)\n")
        joined = " ".join(svg.LAST_WARNINGS)
        self.assertIn("@nowhere", joined)


@unittest.skipUnless(pango.available(), "needs Pango (PyGObject)")
class InlineLayoutTest(unittest.TestCase):
    def setUp(self):
        self.st = TextStyle(font="Source Serif 4", mono="JetBrains Mono", color="#000")

    def lay(self, text, wrap=100.0):
        return layout_block([{"type": "text", "value": text}], self.st, wrap)

    def test_whitespace_collapses(self):
        self.assertAlmostEqual(self.lay("a  b\n c").width, self.lay("a b c").width, places=6)

    def test_breaks_after_hyphens_not_before_digits(self):
        self.assertEqual(self.lay("non-deterministic", 0.01).lines, 2)
        self.assertEqual(self.lay("978-3", 0.01).lines, 1)

    def test_css_line_pitch(self):
        two = layout_block([{"type": "text", "value": "a"}, {"type": "break"},
                            {"type": "text", "value": "b"}], self.st, 100, line_height=1.45)
        self.assertAlmostEqual(two.baselines[1], 1.45, places=6)


if __name__ == "__main__":
    unittest.main()


@unittest.skipUnless(_TOOLCHAIN, "needs Pango (PyGObject) and latex+dvisvgm")
class ShaderBlockTest(unittest.TestCase):
    """`!shader`: parsed into the AST, inlined (with #include) into the deck,
    and the WebGL player shipped only when a deck uses it."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="lemur-shader-")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def build(self, deck, files):
        for name, text in files.items():
            with open(os.path.join(self.tmp, name), "w", encoding="utf-8") as fh:
                fh.write(text)
        path = os.path.join(self.tmp, "deck.lmr")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(deck)
        return svg.build_html(path)[0]

    def test_shader_is_inlined_with_includes(self):
        import base64
        import re as _re
        html = self.build("!slide A\n\n!shader\n\t!src s.glsl\n\t!steps 3\n\t!sound drone\n",
                          {"s.glsl": '#include "c.glsl"\nvoid mainImage(out vec4 c, in vec2 p) { c = vec4(k()); }\n',
                           "c.glsl": "float k() { return 0.5; }\n"})
        m = _re.search(r'data-glsl="([^"]+)"', html)
        self.assertIsNotNone(m)
        src = base64.b64decode(m.group(1)).decode("utf-8")
        self.assertIn("float k()", src)                  # the include was resolved
        self.assertNotIn("#include", src)
        self.assertIn('data-shader-steps="3"', html)
        self.assertIn('data-sound="drone"', html)
        self.assertIn("LMR_PLUGINS", html)               # the player is shipped

    def test_no_player_without_shaders(self):
        html = self.build("!slide A\n\ntext\n", {})
        self.assertNotIn("webgl2", html)

    def test_full_viewport_takes_no_flow_space(self):
        deck = "!slide A\n\n!shader\n\t!src s.glsl\n\t!viewport full\n\n[after]^a\n"
        files = {"s.glsl": "void mainImage(out vec4 c, in vec2 p) { c = vec4(1.0); }\n"}
        captured = []
        orig = svg._TEMPLATES["content"]
        svg._TEMPLATES["content"] = lambda ctx: (orig(ctx), captured.append(ctx.slide))
        try:
            self.build(deck, files)
        finally:
            svg._TEMPLATES["content"] = orig
        (box,) = captured[0].mark_boxes("a")
        self.assertLess(box[1], 400)                     # the text starts right under the title

    def test_missing_shader_warns(self):
        self.build("!slide A\n\n!shader\n\t!src nope.glsl\n", {})
        self.assertTrue(any("nope.glsl" in w for w in svg.LAST_WARNINGS))
