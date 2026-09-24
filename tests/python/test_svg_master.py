"""Tests for the design box (lemur.master Style/Master, style.py) and emit-svg."""

import os
import re
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from lemur import master as mstr  # noqa: E402


class StyleTest(unittest.TestCase):
    """The `class Style` design box -> resolved `Design`, theme inheritance, and
    the shipped Python themes. Stdlib-only (no Pango/LaTeX), so these always run."""

    def test_resolve_design(self):
        from lemur.master import Region, Style, resolve_design

        class S(Style):
            width = 1600
            height = 900
            bg = "#123456"
            body = "#abcdef"
            body_size = 40
            body_region = Region(100, 200, 1400, 500)

        d = resolve_design(S)
        self.assertEqual((d.width, d.height), (1600, 900))
        self.assertEqual(d.bg, "#123456")
        self.assertEqual(d.body, "#abcdef")   # override
        self.assertEqual(d.title, "#232629")  # inherited default
        self.assertEqual(d.body_size, 40.0)
        r = d.body_region
        self.assertEqual((r.x, r.y, r.w, r.h), (100.0, 200.0, 1400.0, 500.0))

    def test_font_string_or_tuple(self):
        from lemur.master import Style, resolve_design

        class S(Style):
            serif = "Foo Serif, serif"

        self.assertEqual(resolve_design(S).serif, ("Foo Serif", "serif"))

    def test_theme_inheritance(self):
        from lemur.master import resolve_design
        from lemur.themes import journal

        class S(journal.Style):
            accent = "#b00020"

        d = resolve_design(S)
        self.assertEqual(d.accent, "#b00020")          # our override
        self.assertEqual(d.serif[0], "Source Serif 4")  # inherited from journal
        self.assertEqual(d.bg, "#fbfaf7")              # inherited from journal

    def test_shipped_python_themes(self):
        self.assertEqual(mstr.theme_names(), ["clean", "dark", "journal"])
        self.assertEqual(mstr.theme_design("dark").bg, "#0d1117")
        self.assertIsNone(mstr.theme_design("nope"))

    def test_default_design(self):
        d = mstr.default_design()
        self.assertEqual(d.bg, "#ffffff")            # the clean default
        self.assertEqual(d.body_region.x, 96.0)


# Toolchain-gated: building/wireframe needs Pango + LaTeX.
try:
    from lemur.typeset import pango as _pango
    import shutil as _sh
    _TOOLCHAIN = _pango.available() and _sh.which("latex") and _sh.which("dvisvgm")
except Exception:
    _TOOLCHAIN = False


@unittest.skipUnless(_TOOLCHAIN, "needs Pango (PyGObject) and latex+dvisvgm")
class MasterAppliesTest(unittest.TestCase):
    def test_custom_style_changes_output(self):
        from lemur.emit import svg
        from lemur.master import Region, Style, resolve_design

        class S(Style):
            bg = "#fafafa"
            body_region = Region(300, 400, 1300, 500)

        with tempfile.TemporaryDirectory(prefix="lemur-mapply-") as d:
            src = os.path.join(d, "deck.lmr")
            with open(src, "w", encoding="utf-8") as fh:
                fh.write("# Hi\n\nsome body text\n")
            out = os.path.join(d, "deck.html")
            svg.build(src, out, design=resolve_design(S()))   # a Style-derived Master
            html = open(out, encoding="utf-8").read()
        self.assertIn('fill="#fafafa"', html)  # the style's bg reached the SVG

    def test_wireframe_renders_regions(self):
        from lemur.emit import svg
        html = svg.wireframe_html(mstr.default_design())
        self.assertIn("stroke-dasharray", html)   # dashed region boxes
        self.assertIn("<use ", html)               # region labels as baked glyphs


@unittest.skipUnless(_TOOLCHAIN, "needs Pango (PyGObject) and latex+dvisvgm")
class ThemeVisualTest(unittest.TestCase):
    """The bundled fonts are registered (so output matches the browser emitter),
    variable weights work, and code is syntax-highlighted from theme colours."""

    def test_bundled_fonts_registered(self):
        self.assertTrue(_pango.font_exists("Source Sans 3"))
        self.assertTrue(_pango.font_exists("JetBrains Mono"))

    def test_variable_weight_differs(self):
        def ink(s):
            return sum((sp[:, 0].max() - sp[:, 0].min()) * (sp[:, 1].max() - sp[:, 1].min())
                       for cl in s.clusters for sp in cl.subpaths if len(sp))
        light = _pango.shape("Weight", font="Source Sans 3", weight="normal")
        heavy = _pango.shape("Weight", font="Source Sans 3", weight=800)
        self.assertGreater(ink(heavy), ink(light))

    def test_code_is_highlighted(self):
        from lemur.emit import svg
        with tempfile.TemporaryDirectory(prefix="lemur-hl-") as d:
            src = os.path.join(d, "c.lmr")
            with open(src, "w", encoding="utf-8") as fh:
                fh.write("!slide Code\n\n:: python\n    def f(x):\n        return 42\n")
            out = os.path.join(d, "c.html")
            svg.build(src, out)
            html = open(out, encoding="utf-8").read()
        # the clean palette's keyword colour must appear (def/return highlighted)
        self.assertIn('fill="#a3562a"', html)
        colours = set(re.findall(r'fill="(#[0-9a-f]{6})"', html))
        self.assertGreaterEqual(len(colours), 3)   # not a single flat colour


@unittest.skipUnless(_TOOLCHAIN, "needs Pango (PyGObject) and latex+dvisvgm")
class TemplateSystemTest(unittest.TestCase):
    """User-defined slide templates: a deck's style.py registers a template and a
    `!slide[.name]` variant selects it."""

    def test_custom_template_selected_by_variant(self):
        from lemur.emit import svg
        with tempfile.TemporaryDirectory(prefix="lemur-tpl-") as d:
            with open(os.path.join(d, "style.py"), "w", encoding="utf-8") as fh:
                fh.write(
                    "from lemur.style import register, flow\n"
                    "@register('banner')\n"
                    "def banner(ctx):\n"
                    "    ctx.slide.add_rect(0, 0, ctx.design.width, 100, '#123456')\n"
                    "    flow(ctx, ctx.blocks, (100.0, ctx.design.width - 200), 200.0)\n"
                )
            src = os.path.join(d, "deck.lmr")
            with open(src, "w", encoding="utf-8") as fh:
                fh.write("!slide[.banner] Hi\n\nbody\n")
            out = os.path.join(d, "deck.html")
            svg.build(src, out)                      # style.py auto-loaded from the folder
            html = open(out, encoding="utf-8").read()
        self.assertIn('fill="#123456"', html)        # the custom template drew its band
        self.assertNotIn("banner", svg._TEMPLATES)   # registrations don't leak (isolated per build)

    def test_template_for_precedence(self):
        from lemur.emit import svg
        self.assertIs(svg._template_for("content", ["section"]), svg._TEMPLATES["section"])
        self.assertIs(svg._template_for("section", ["nope"]), svg._TEMPLATES["section"])
        self.assertIs(svg._template_for("mystery", None), svg._TEMPLATES["content"])

    def test_section_subtitle_from_h2(self):
        # A `## subheader` right after `# header` is consumed by the section
        # template as a centred subtitle, not left-flowed as a heading block.
        from lemur.emit import svg
        with tempfile.TemporaryDirectory(prefix="lemur-sec-") as d:
            src = os.path.join(d, "deck.lmr")
            with open(src, "w", encoding="utf-8") as fh:
                fh.write("# Section\n\n## Subtitle here\n\n!slide Body\n\ntext\n")
            out = os.path.join(d, "deck.html")
            svg.build(src, out)
            html = open(out, encoding="utf-8").read()
        # section slide is the second slide (after the cover-less first) and renders glyphs
        self.assertIn("<use ", html)
        self.assertGreaterEqual(html.count('class="slide"'), 2)


@unittest.skipUnless(_TOOLCHAIN, "needs Pango (PyGObject) and latex+dvisvgm")
class ParityFeaturesTest(unittest.TestCase):
    """Old-presenter parity (Plan-SVG §8b): block/inline constructs, chrome from
    the `presentation` block, variant modifiers, and transitions."""

    def _build(self, src_text):
        from lemur.emit import svg
        with tempfile.TemporaryDirectory(prefix="lemur-parity-") as d:
            src = os.path.join(d, "deck.lmr")
            with open(src, "w", encoding="utf-8") as fh:
                fh.write(src_text)
            out = os.path.join(d, "deck.html")
            svg.build(src, out)
            with open(out, encoding="utf-8") as fh:
                return fh.read()

    def test_env_renders_accent_rule(self):
        # a `!theorem` draws a left rule in the accent colour (clean = #2e5e6e)
        html = self._build("!slide S\n\n!theorem T\n\tbody\n")
        self.assertIn('fill="#2e5e6e"', html)

    def test_spacer_pushes_content(self):
        # a fixed gap adds vertical space: the deck builds and keeps both paras
        html = self._build("!slide S\n\ntop\n\n!gap[3em]\n\nbottom\n")
        self.assertIn("<use ", html)

    def test_style_block_colours(self):
        html = self._build("!slide S\n\n!style[#2e7d32]\n\tgreen text\n")
        self.assertIn('fill="#2e7d32"', html)

    def test_inline_span_colour(self):
        html = self._build("!slide S\n\nA [red bit]{#cc0000} here.\n")
        self.assertIn('fill="#cc0000"', html)

    def test_inline_code_chip(self):
        # inline `code` draws a chip in the panel colour (clean = #f2f2f2)
        html = self._build("!slide S\n\ntext with `inline` code.\n")
        self.assertIn('fill="#f2f2f2"', html)

    def test_aspect_4_3(self):
        html = self._build("!aspect 4:3\n\n!slide S\n\nbody\n")
        self.assertIn('viewBox="0 0 1440 1080"', html)

    def test_transition_and_progress_config(self):
        html = self._build("!transition slide rise\n!progress bottom\n\n!slide S\n\nbody\n")
        self.assertIn('"across":"slide"', html)
        self.assertIn('"step":"rise"', html)
        self.assertIn('"progress":"bottom"', html)

    def test_slidenumbers_off(self):
        on = self._build("!slide A\n\na\n\n!slide B\n\nb\n")
        off = self._build("!slidenumbers off\n\n!slide A\n\na\n\n!slide B\n\nb\n")
        self.assertLess(off.count("<use "), on.count("<use "))   # the "n / n" glyphs are gone

    def test_chrome_images_embedded(self):
        from lemur.emit import svg
        with tempfile.TemporaryDirectory(prefix="lemur-chrome-") as d:
            # a 1x1 png stands in for the logo / title image
            png = ("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk"
                   "+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==")
            import base64
            for name in ("logo.png", "hero.png"):
                with open(os.path.join(d, name), "wb") as fh:
                    fh.write(base64.b64decode(png))
            src = os.path.join(d, "deck.lmr")
            with open(src, "w", encoding="utf-8") as fh:
                fh.write("!title T\n!logo logo.png\n!titleimage hero.png\n\n!slide S\n\nbody\n")
            out = os.path.join(d, "deck.html")
            svg.build(src, out)
            html = open(out, encoding="utf-8").read()
        self.assertGreaterEqual(html.count("<image "), 2)   # cover hero + a logo

    def test_dark_variant(self):
        html = self._build("!slide[.dark] Dark\n\nbody\n")
        self.assertIn('fill="#14171c"', html)               # the dark slide ground

    def test_variant_modifier_is_not_a_template(self):
        from lemur.emit import svg
        # `.center` is a modifier, not a template → still the content template
        self.assertNotIn("center", svg._TEMPLATES)
        tname, mods = svg._split_variant(["center", "middle"])
        self.assertIsNone(tname)
        self.assertEqual(set(mods), {"center", "middle"})


@unittest.skipUnless(_TOOLCHAIN, "needs Pango (PyGObject) and latex+dvisvgm")
class StyleFileTest(unittest.TestCase):
    """A deck's `style.py` (design box + templates in one file), auto-loaded from
    the deck's folder, and isolated so its registrations don't leak."""

    STYLE = (
        "from lemur.style import Style, register, flow\n"
        "class Style(Style):\n"
        "    bg = '#101820'\n"
        "    title = '#e8eef4'\n"
        "@register('content')\n"
        "def content(ctx):\n"
        "    ctx.slide.add_rect(0, 0, ctx.design.width, 90, '#ff5a5f')\n"
        "    flow(ctx, ctx.blocks, (120.0, ctx.design.width - 240), 200.0)\n"
    )

    def test_auto_style_py_is_picked_up(self):
        from lemur.emit import svg
        with tempfile.TemporaryDirectory(prefix="lemur-style-") as d:
            with open(os.path.join(d, "style.py"), "w", encoding="utf-8") as fh:
                fh.write(self.STYLE)
            src = os.path.join(d, "deck.lmr")
            with open(src, "w", encoding="utf-8") as fh:
                fh.write("!slide S\n\nbody\n")
            out = os.path.join(d, "deck.html")
            svg.build(src, out)                       # no --master/--style: auto style.py
            html = open(out, encoding="utf-8").read()
        self.assertIn('viewBox="0 0 1920 1080"', html)
        self.assertIn('--bg:#101820', html)           # design() colour reached the theme
        self.assertIn('fill="#ff5a5f"', html)         # the style.py content template drew its band

    def test_registrations_do_not_leak(self):
        from lemur.emit import svg
        builtin = svg._TEMPLATES.get("content")
        with tempfile.TemporaryDirectory(prefix="lemur-style2-") as d:
            with open(os.path.join(d, "style.py"), "w", encoding="utf-8") as fh:
                fh.write(self.STYLE)
            src = os.path.join(d, "deck.lmr")
            with open(src, "w", encoding="utf-8") as fh:
                fh.write("!slide S\n\nbody\n")
            svg.build(src, os.path.join(d, "deck.html"))
        # after the build the global registry is back to the built-in content template
        self.assertIs(svg._TEMPLATES.get("content"), builtin)


@unittest.skipUnless(_TOOLCHAIN, "needs Pango (PyGObject) and latex+dvisvgm")
class QualityAndLetterboxTest(unittest.TestCase):
    """`--quality` sets emitted coordinate precision; each slide carries its own
    background so a mismatched display letterboxes seamlessly."""

    def _build(self, deck, **kw):
        from lemur.emit import svg
        with tempfile.TemporaryDirectory(prefix="lemur-ql-") as d:
            src = os.path.join(d, "x.lmr")
            with open(src, "w", encoding="utf-8") as fh:
                fh.write(deck)
            out = os.path.join(d, "x.html")
            svg.build(src, out, **kw)
            return open(out, encoding="utf-8").read()

    def test_quality_changes_precision(self):
        import re
        from lemur.typeset import geometry
        deck = "!slide S\n\nsome wavy text\n"
        try:
            geometry.set_precision(2)
            draft = self._build(deck)
            geometry.set_precision(6)
            hi = self._build(deck)
        finally:
            geometry.set_precision(4)             # restore the default
        dec = lambda h: max((len(n.split(".")[1]) for n in re.findall(r"-?\d+\.\d+",
                             " ".join(re.findall(r'<path id="[^"]+" d="([^"]+)"', h)))), default=0)
        self.assertLessEqual(dec(draft), 2)
        self.assertGreater(dec(hi), dec(draft))

    def test_each_slide_carries_its_background(self):
        # a normal slide's container bg is the theme ground (so the letterbox matches)
        html = self._build("!slide A\n\na\n\n!slide B\n\nb\n")
        self.assertEqual(html.count('class="slide" style="background:#ffffff"'), 2)


if __name__ == "__main__":
    unittest.main()
