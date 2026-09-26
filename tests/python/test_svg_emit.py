"""Tests for the build-time SVG emitter (lemur.emit.svg).

These exercise the whole seam — parser -> AST -> layout -> Pango/LaTeX typeset ->
baked SVG -> one self-contained HTML — so they need the heavy native toolchain
(Pango via PyGObject, and `latex` + `dvisvgm`). When any of it is missing the
tests skip cleanly rather than fail, keeping the stdlib-only parser suite
runnable everywhere (Plan-SVG §9).
"""

import os
import re
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from lemur.emit import svg  # noqa: E402
from lemur.typeset import latex, pango  # noqa: E402


def _example():
    here = os.path.dirname(__file__)
    return os.path.join(here, "..", "..", "examples", "math", "deck.lmr")


_HAVE_PANGO = pango.available()
_HAVE_TEX = shutil.which("latex") is not None and shutil.which("dvisvgm") is not None
_TOOLCHAIN = _HAVE_PANGO and _HAVE_TEX


@unittest.skipUnless(_TOOLCHAIN, "needs Pango (PyGObject) and latex+dvisvgm")
class SvgEmitTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.mkdtemp(prefix="lemur-svgtest-")
        cls.out = os.path.join(cls._tmp, "deck.html")
        svg.build(_example(), cls.out)
        with open(cls.out, encoding="utf-8") as fh:
            cls.html = fh.read()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls._tmp, ignore_errors=True)

    def test_single_self_contained_file(self):
        # One HTML file with an inline <svg>; nothing else is written beside it.
        self.assertIn("<svg", self.html)
        self.assertEqual(os.listdir(self._tmp), ["deck.html"])

    def test_no_display_time_dependencies(self):
        low = self.html.lower()
        self.assertNotIn("mathjax", low)
        for ext in (".woff", ".woff2", ".ttf", ".otf"):
            self.assertNotIn(ext, low)
        # The only URL may be the SVG namespace; no fetched resource.
        for url in re.findall(r"https?://[^\s\"')]+", self.html):
            self.assertEqual(url, "http://www.w3.org/2000/svg", f"unexpected URL {url!r}")

    def test_everything_is_vector(self):
        # Text and maths are baked outlines: <defs> shapes placed by <use>.
        self.assertIn("<defs>", self.html)
        self.assertIn("<use ", self.html)
        self.assertNotIn("<image", self.html)  # this demo has no rasters

    def test_glyph_dedup(self):
        placements = self.html.count("<use ")
        distinct = self.html.count("<path id=")
        self.assertGreater(placements, 0)
        self.assertGreater(distinct, 0)
        # Repeated glyphs must actually be shared, not re-emitted.
        self.assertLess(distinct, placements)

    def test_step_reveal_present(self):
        # The display equation is gated to a build step (opacity track, trivial form).
        self.assertRegex(self.html, r'data-step="[1-9]')
        self.assertIn("opacity", self.html)

    def test_deterministic(self):
        with tempfile.TemporaryDirectory(prefix="lemur-svgdet-") as d:
            second = os.path.join(d, "again.html")
            svg.build(_example(), second)
            with open(second, encoding="utf-8") as fh:
                other = fh.read()
        self.assertEqual(self.html, other, "rebuild is not byte-identical")


@unittest.skipUnless(_TOOLCHAIN, "needs Pango (PyGObject) and latex+dvisvgm")
class SvgFeaturesTest(unittest.TestCase):
    """The richer deck: styled paragraph, inline maths, lists, a code block."""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.mkdtemp(prefix="lemur-svgfeat-")
        out = os.path.join(cls._tmp, "feat.html")
        here = os.path.dirname(__file__)
        svg.build(os.path.join(here, "..", "..", "examples", "code", "deck.lmr"), out)
        with open(out, encoding="utf-8") as fh:
            cls.html = fh.read()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls._tmp, ignore_errors=True)

    def test_code_block_has_panel(self):
        # Background rect + the code panel rect => at least two <rect>.
        self.assertGreaterEqual(self.html.count("<rect "), 2)

    def test_content_present(self):
        self.assertIn("<use ", self.html)
        self.assertIn("<defs>", self.html)
        self.assertLess(self.html.count("<path id="), self.html.count("<use "))

    def test_no_display_time_dependencies(self):
        low = self.html.lower()
        self.assertNotIn("mathjax", low)
        for ext in (".woff", ".woff2", ".ttf", ".otf"):
            self.assertNotIn(ext, low)


@unittest.skipUnless(_TOOLCHAIN, "needs Pango (PyGObject) and latex+dvisvgm")
class SvgPaginationTest(unittest.TestCase):
    """Multi-slide pagination, per-slide id namespacing, and reveal steps."""

    DECK = (
        "# One\n\nAlways shown.\n\n!pause\n\nRevealed second.\n\n"
        "- base item\n+ stepped item\n\n# Two\n\nSecond slide body.\n"
    )

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.mkdtemp(prefix="lemur-svgpag-")
        src = os.path.join(cls._tmp, "deck.lmr")
        with open(src, "w", encoding="utf-8") as fh:
            fh.write(cls.DECK)
        out = os.path.join(cls._tmp, "deck.html")
        svg.build(src, out)
        with open(out, encoding="utf-8") as fh:
            cls.html = fh.read()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls._tmp, ignore_errors=True)

    def test_two_slides(self):
        self.assertEqual(self.html.count('class="slide"'), 2)
        self.assertIn('id="nav"', self.html)            # navigation wedges present
        self.assertIn('class="nav-btn nav-next"', self.html)

    def test_outlines_are_shared_across_slides(self):
        # One deck-wide outline store: every glyph once, every <use> resolves,
        # and no id is defined twice (slides no longer carry their own copies).
        ids = re.findall(r'<path id="(g\d+)"', self.html)
        self.assertTrue(ids)
        self.assertEqual(len(ids), len(set(ids)))
        self.assertIn('class="lmr-defs"', self.html)
        refs = set(re.findall(r'<use href="#(g\d+)"', self.html))
        self.assertTrue(refs)
        self.assertLessEqual(refs, set(ids))

    def test_reveals_from_spec(self):
        # `!pause` and `+` produce step gates; nothing is auto-revealed anymore.
        self.assertRegex(self.html, r'data-step="[1-9]')


@unittest.skipUnless(_TOOLCHAIN, "needs Pango (PyGObject) and latex+dvisvgm")
class SvgColumnsTest(unittest.TestCase):
    """Columns split the region horizontally; content lands in both halves."""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.mkdtemp(prefix="lemur-svgcol-")
        out = os.path.join(cls._tmp, "cols.html")
        here = os.path.dirname(__file__)
        svg.build(os.path.join(here, "..", "..", "examples", "columns", "deck.lmr"), out)
        with open(out, encoding="utf-8") as fh:
            cls.html = fh.read()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls._tmp, ignore_errors=True)

    def test_content_in_both_halves(self):
        # <use> matrices carry the x-translate (5th component); a two-column
        # layout must place glyphs in both the left and right half of the 1920 box.
        xs = [float(m) for m in re.findall(r"matrix\([^,]+,[^,]+,[^,]+,[^,]+,([-\d.]+),", self.html)]
        self.assertTrue(xs, "no <use> matrices found")
        self.assertTrue(any(x < 700 for x in xs), "nothing in the left column")
        self.assertTrue(any(x > 1000 for x in xs), "nothing in the right column")


@unittest.skipUnless(_TOOLCHAIN, "needs Pango (PyGObject) and latex+dvisvgm")
class SvgStackTest(unittest.TestCase):
    """Stacked layers gate on a step range, so one replaces the previous."""

    DECK = (
        "# S\n\n!stack\n"
        "\t!layer<1>\n\t\tfirst layer\n"
        "\t!layer<2->\n\t\tsecond layer\n"
    )

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.mkdtemp(prefix="lemur-svgstk-")
        src = os.path.join(cls._tmp, "s.lmr")
        with open(src, "w", encoding="utf-8") as fh:
            fh.write(cls.DECK)
        out = os.path.join(cls._tmp, "s.html")
        svg.build(src, out)
        with open(out, encoding="utf-8") as fh:
            cls.html = fh.read()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls._tmp, ignore_errors=True)

    def test_disappear_gate(self):
        # layer<1> is visible only at step 1 -> a data-until gate must appear.
        self.assertRegex(self.html, r'data-step="1" data-until="1"')
        self.assertRegex(self.html, r'data-step="2"')


@unittest.skipUnless(_TOOLCHAIN, "needs Pango (PyGObject) and latex+dvisvgm")
class SvgTableFigureTest(unittest.TestCase):
    """Tables (rules + aligned cells) and figures (data-URI embed) — now two
    standalone example decks (examples/tables, examples/figures)."""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.mkdtemp(prefix="lemur-svgtf-")
        here = os.path.dirname(__file__)
        cls.tsrc = os.path.join(here, "..", "..", "examples", "tables", "deck.lmr")
        cls.fsrc = os.path.join(here, "..", "..", "examples", "figures", "deck.lmr")
        tout = os.path.join(cls._tmp, "t.html")
        fout = os.path.join(cls._tmp, "f.html")
        svg.build(cls.tsrc, tout)
        svg.build(cls.fsrc, fout)
        with open(tout, encoding="utf-8") as fh:
            cls.thtml = fh.read()
        with open(fout, encoding="utf-8") as fh:
            cls.fhtml = fh.read()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls._tmp, ignore_errors=True)

    def test_table_has_rules(self):
        # a header rule + a light separator (and the strong `---` rule).
        self.assertGreaterEqual(self.thtml.count("<rect "), 2)

    def test_figure_embedded_as_data_uri(self):
        self.assertIn("<image ", self.fhtml)
        self.assertIn('href="data:image/svg+xml;base64,', self.fhtml)

    def test_no_external_reference(self):
        self.assertNotIn("figs/", self.fhtml)  # the src path never leaks out
        for url in re.findall(r'https?://[^\s"\')]+', self.fhtml):
            self.assertEqual(url, "http://www.w3.org/2000/svg", f"unexpected URL {url!r}")

    def test_deterministic(self):
        with tempfile.TemporaryDirectory(prefix="lemur-tfdet-") as d:
            other = os.path.join(d, "again.html")
            svg.build(self.fsrc, other)
            with open(other, encoding="utf-8") as fh:
                self.assertEqual(self.fhtml, fh.read())


@unittest.skipUnless(_TOOLCHAIN, "needs Pango (PyGObject) and latex+dvisvgm")
class SvgArrowsTest(unittest.TestCase):
    """annotate/connect draw build-time arrows anchored to real glyph boxes."""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.mkdtemp(prefix="lemur-svgarr-")
        out = os.path.join(cls._tmp, "arr.html")
        here = os.path.dirname(__file__)
        svg.build(os.path.join(here, "..", "..", "examples", "annotations", "deck.lmr"), out)
        with open(out, encoding="utf-8") as fh:
            cls.html = fh.read()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls._tmp, ignore_errors=True)

    def test_arrows_drawn(self):
        # Two annotate arrows + one connect arrow. Each is a stroked curve; that
        # they exist at all means every mark resolved to a real box at build time.
        self.assertGreaterEqual(self.html.count('stroke-width="3.5"'), 3)

    def test_arrows_are_gated(self):
        # Each annotate item / connect link reveals on its own step.
        self.assertRegex(self.html, r'data-step="[1-9]')

    def test_unresolved_mark_does_not_crash(self):
        with tempfile.TemporaryDirectory(prefix="lemur-arrbad-") as d:
            src = os.path.join(d, "bad.lmr")
            with open(src, "w", encoding="utf-8") as fh:
                fh.write("# X\n\nA [thing]^here.\n\n!connect\n\there -> nowhere\n")
            out = os.path.join(d, "bad.html")
            svg.build(src, out)  # must not raise even though `nowhere` has no mark
            self.assertTrue(os.path.exists(out))


@unittest.skipUnless(_TOOLCHAIN, "needs Pango (PyGObject) and latex+dvisvgm")
class SvgBaselineTest(unittest.TestCase):
    """Text is anchored on its typographic baseline (font metric), not its glyph
    bounding box — so ascenders/descenders don't shift a block's position."""

    def _title_ys(self, deck: str):
        with tempfile.TemporaryDirectory(prefix="lemur-base-") as d:
            src = os.path.join(d, "d.lmr")
            with open(src, "w", encoding="utf-8") as fh:
                fh.write(deck)
            out = os.path.join(d, "d.html")
            svg.build(src, out)
            html = open(out, encoding="utf-8").read()
        ys = []
        for s in re.findall(r'<div class="slide"[^>]*>(.*?)</div>\s*(?=<div class="slide"|<nav id="nav")', html, re.S):
            m = re.search(r'<use [^>]*transform="matrix\(([^)]+)\)"', s)
            ys.append(float(m.group(1).split(",")[5]))
        return ys

    def test_title_baseline_content_independent(self):
        # Both titles start with 'X' (same glyph, same outline origin), so an
        # identical placement y proves the baseline is the same despite the
        # descenders in the second title.
        ys = self._title_ys("# Xoo\n\nx\n\n# Xgypq\n\ny\n")
        self.assertEqual(len(ys), 2)
        self.assertAlmostEqual(ys[0], ys[1], places=4)


@unittest.skipUnless(_TOOLCHAIN, "needs Pango (PyGObject) and latex+dvisvgm")
class SvgViewerTest(unittest.TestCase):
    """The display runtime ships the presenter features of the old viewer:
    nav, step reveals, the grid ('o') and sidebar ('O') overviews, and print."""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.mkdtemp(prefix="lemur-view-")
        src = os.path.join(cls._tmp, "d.lmr")
        with open(src, "w", encoding="utf-8") as fh:
            fh.write("# One\n\na\n\n# Two\n\nb\n")
        out = os.path.join(cls._tmp, "d.html")
        svg.build(src, out)
        with open(out, encoding="utf-8") as fh:
            cls.html = fh.read()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls._tmp, ignore_errors=True)

    def test_overview_present(self):
        # grid + sidebar overview, and their key bindings, are inlined.
        self.assertIn("openOverview", self.html)
        self.assertIn("#ov-grid", self.html)         # overview CSS
        self.assertIn("'o'", self.html)              # grid key
        self.assertIn("'O'", self.html)              # sidebar key
        self.assertIn("'Escape'", self.html)         # close

    def test_navigation_and_steps(self):
        self.assertIn("ArrowRight", self.html)
        self.assertIn("data-step", self.html) or self.assertIn("[data-step]", self.html)

    def test_print_media(self):
        self.assertIn("@media print", self.html)


@unittest.skipUnless(_TOOLCHAIN, "needs Pango (PyGObject) and latex+dvisvgm")
class SvgMasterDeckTest(unittest.TestCase):
    """The full example deck exercises cover synthesis, section dividers,
    math-mark annotations, references, URL labels, and an embedded figure."""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.mkdtemp(prefix="lemur-deck-")
        here = os.path.dirname(__file__)
        cls.src = os.path.join(here, "..", "..", "examples", "lecture", "master.lmr")
        out = os.path.join(cls._tmp, "d.html")
        svg.build(cls.src, out)
        with open(out, encoding="utf-8") as fh:
            cls.html = fh.read()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls._tmp, ignore_errors=True)

    def test_url_labels_embedded(self):
        self.assertIn("window.LMR", self.html)         # slide/step + deep-link map
        self.assertIn('"sum_product"', self.html)       # a slide label is in the map

    def test_cover_added(self):
        # a synthesized cover means one more slide than there are pagebreaks
        breaks = open(self.src, encoding="utf-8").read()  # not exact, so just sanity
        self.assertGreaterEqual(self.html.count('class="slide"'), 3)

    def test_annotations_and_arrows_drawn(self):
        # \mk marks inside maths are located, so annotate/connect arrows exist
        self.assertGreater(self.html.count('stroke-width="3.5"'), 0)

    def test_figure_embedded(self):
        self.assertIn("data:image", self.html)

    def test_separate_images_writes_folder(self):
        with tempfile.TemporaryDirectory(prefix="lemur-sep-") as d:
            out = os.path.join(d, "deck")
            svg.build(self.src, out, embed_images=False)
            self.assertTrue(os.path.isdir(os.path.join(out, "images")))
            self.assertTrue(os.listdir(os.path.join(out, "images")))  # image(s) copied
            html = open(os.path.join(out, "index.html"), encoding="utf-8").read()
            self.assertIn('href="images/', html)
            self.assertNotIn("data:image", html)


@unittest.skipUnless(_TOOLCHAIN, "needs Pango (PyGObject) and latex+dvisvgm")
class SvgAnnotateThemeTest(unittest.TestCase):
    """Colour-only annotations recolour their mark; code line-highlights gate to
    steps; named themes and `!theme` change the palette."""

    def _build(self, deck, **kw):
        from lemur.emit import svg
        with tempfile.TemporaryDirectory(prefix="lemur-at-") as d:
            src = os.path.join(d, "x.lmr")
            with open(src, "w", encoding="utf-8") as fh:
                fh.write(deck)
            out = os.path.join(d, "x.html")
            svg.build(src, out, **kw)
            return open(out, encoding="utf-8").read()

    def test_colour_only_annotation_recolours_without_arrow(self):
        html = self._build(
            "!slide A\n\nThe [important bit]^k stands out.\n\n!annotate\n\tk[#c0392b]:\n"
        )
        self.assertIn('fill="#c0392b"', html)             # the mark got recoloured
        self.assertNotIn('stroke-width="3.5"', html)      # colour-only => no arrow

    def test_code_line_highlight_only_during_step(self):
        # two groups: the first must stop highlighting when the second begins,
        # i.e. it is bounded (data-until), not persistent.
        html = self._build(
            "!slide C\n\n:: python[1|2]\n\tdef f():\n\t\treturn 1\n"
        )
        self.assertIn("fill-opacity", html)               # highlight/dim rects exist
        self.assertRegex(html, r'data-step="1" data-until="1"')  # group 1 is only-step-1

    def test_named_theme_changes_background(self):
        from lemur.master import theme_design
        html = self._build("!slide D\n\nx\n", design=theme_design("dark"))
        self.assertIn('fill="#0d1117"', html)             # dark theme bg


@unittest.skipUnless(_HAVE_PANGO, "needs Pango (PyGObject)")
class SvgMadeWithTest(unittest.TestCase):
    """`!madewith`: the wordmark (and the logo, when the package has one) on the
    first slide only."""

    def build(self, config: str, logo: str) -> "tuple[str, int]":
        with tempfile.TemporaryDirectory(prefix="lemur-madewith-") as d:
            src = os.path.join(d, "deck.lmr")
            with open(src, "w", encoding="utf-8") as fh:
                fh.write(config + "\n!slide One\n\nx\n\n!slide Two\n\ny\n")
            keep, svg.LEMUR_LOGO = svg.LEMUR_LOGO, logo
            try:
                page, (placements, _) = svg.build_html(src)
            finally:
                svg.LEMUR_LOGO = keep
        return page, placements

    def test_wordmark_and_logo_on_the_first_slide(self):
        with tempfile.TemporaryDirectory(prefix="lemur-logo-") as d:
            logo = os.path.join(d, "logo.svg")
            with open(logo, "w", encoding="utf-8") as fh:
                fh.write('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 10">'
                         '<rect width="20" height="10" fill="currentColor"/></svg>')
            plain, n0 = self.build("!title T", logo)
            marked, n1 = self.build("!title T\n!madewith", logo)
            bare, n2 = self.build("!title T\n!madewith", os.path.join(d, "missing.svg"))
        self.assertGreater(n1, n0)                     # the wordmark's glyphs
        self.assertEqual(n1, n2)                       # the same text, with or without the logo
        self.assertNotIn("<image", marked)             # the logo is vector, in place
        slides = marked.split('class="slide"')
        self.assertEqual(sum('viewBox="0 0 20 10"' in sl for sl in slides), 1)   # on the first slide only
        self.assertIn('viewBox="0 0 20 10"', slides[1])
        self.assertNotIn("currentColor", marked)                   # tinted like the wordmark
        self.assertNotIn('viewBox="0 0 20 10"', bare)


class SvgEmitSkipGuardTest(unittest.TestCase):
    """A smoke test that always runs: the emitter module imports without the
    native deps present (they are only touched at build time)."""

    def test_module_imports(self):
        self.assertTrue(hasattr(svg, "build"))
        self.assertTrue(hasattr(latex, "tex_glyphs"))
        self.assertTrue(hasattr(pango, "shape"))


try:
    import numpy  # noqa: F401
    _HAVE_NUMPY = True
except Exception:
    _HAVE_NUMPY = False

try:
    import matplotlib  # noqa: F401
    _HAVE_MPL = True
except Exception:
    _HAVE_MPL = False


@unittest.skipUnless(_TOOLCHAIN and _HAVE_NUMPY, "needs Pango + latex + numpy")
class SvgWorldAnimTest(unittest.TestCase):
    """3-D `View` shapes ship world geometry the player projects; the baked still
    frame is projected at build time with the final camera, and the projector
    (svg/world.js) is inlined only into decks that need it."""

    ANIM = (
        "import numpy as np\n"
        "from lemur.anim import Anim, FadeIn, View\n\n"
        "class Orbit(Anim):\n"
        "    def build(self):\n"
        "        v = View(azim=0, elev=20, scale=1.0)\n"
        "        v.occluder = {'c': [0.0, 0.0, 0.0], 'R': 1.0, 'cap': None}\n"
        "        a = v.dot((0.0, -1.0, 0.0), rule='hide')\n"
        "        b = v.dot((0.0, 1.0, 0.0), rule='hide', color='#00ff00')\n"
        "        ring = v.curve_fn(lambda: [(1.01 * np.cos(t), 1.01 * np.sin(t), 0.0)\n"
        "                                   for t in np.linspace(0, 2 * np.pi, 60)], closed=True, rule='vis')\n"
        "        self.play(FadeIn(a), FadeIn(b), FadeIn(ring))\n"
        "        self.play(*v.reorient(azim=180), run_time=1.0)\n"
        "        self.next()\n"
    )

    def _build(self, deck, files):
        tmp = tempfile.mkdtemp(prefix="lemur-svgworld-")
        self.addCleanup(shutil.rmtree, tmp, True)
        for name, text in files.items():
            with open(os.path.join(tmp, name), "w", encoding="utf-8") as fh:
                fh.write(text)
        src, out = os.path.join(tmp, "deck.lmr"), os.path.join(tmp, "deck.html")
        with open(src, "w", encoding="utf-8") as fh:
            fh.write(deck)
        svg.build(src, out)
        with open(out, encoding="utf-8") as fh:
            return fh.read()

    def test_final_camera_decides_the_still(self):
        import html as H
        import json
        import re

        page = self._build("!slide Orbit\n\n!anim\n\t!src orbit.py\n", {"orbit.py": self.ANIM})
        self.assertIn("window.LMRW = LMRW", page)                 # the projector came along
        data = json.loads(H.unescape(re.search(r"data-anim='([^']*)'", page).group(1)))
        self.assertTrue(data["views"])
        for n in data["nodes"]:
            if n.get("wk") != "anchor":
                continue
            tag = re.search(r'<[^>]*data-i="%d"[^>]*>' % n["i"], page).group(0)
            # after the half orbit the +y dot faces the camera and the -y one is behind
            self.assertEqual("display:none" in tag, n["s"]["a3"][1] < 0, tag)

    def test_projector_only_when_needed(self):
        page = self._build("!slide Plain\n\nNo animation here.\n", {})
        self.assertNotIn("window.LMRW = LMRW", page)


@unittest.skipUnless(_TOOLCHAIN and _HAVE_NUMPY, "needs Pango + latex + numpy")
class SvgAnimTest(unittest.TestCase):
    """`!anim` runs its `!src` module at build time and bakes the keyframe IR
    into a viewport: a clipped camera group with `<path data-i>`s and a
    `data-anim` blob the runtime plays, its beats folded into the slide steps."""

    ANIM = (
        "from lemur.anim import Anim, Circle, Create, RIGHT\n\n"
        "class Spike(Anim):\n"
        "    def build(self):\n"
        "        c = Circle(radius=1.0)\n"
        "        self.play(Create(c))\n"
        "        self.next()\n"
        "        self.play(c.animate.shift(RIGHT * 2))\n"
        "        self.next()\n"
    )
    DECK = "!slide An animation\n\n!anim\n\t!src circle.py\n"

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.mkdtemp(prefix="lemur-svganim-")
        with open(os.path.join(cls._tmp, "circle.py"), "w", encoding="utf-8") as fh:
            fh.write(cls.ANIM)
        src = os.path.join(cls._tmp, "deck.lmr")
        with open(src, "w", encoding="utf-8") as fh:
            fh.write(cls.DECK)
        out = os.path.join(cls._tmp, "deck.html")
        svg.build(src, out)
        with open(out, encoding="utf-8") as fh:
            cls.html = fh.read()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls._tmp, ignore_errors=True)

    def test_viewport_group_baked(self):
        self.assertIn('class="lmr-anim"', self.html)          # the anim wrapper
        self.assertIn('class="anim-cam"', self.html)          # world->viewport camera group
        self.assertRegex(self.html, r'<clipPath id="vp\d+">')  # viewport clip
        self.assertRegex(self.html, r'<path data-i="0"')       # the baked circle, by index

    def test_ir_embedded_for_runtime(self):
        m = re.search(r"data-anim='(\{.*?\})'", self.html)
        self.assertIsNotNone(m)
        import json
        data = json.loads(m.group(1))
        self.assertEqual(data["beats"], [1.0, 2.0])            # two self.next() beats
        self.assertEqual(len(data["nodes"]), 1)                # one circle
        self.assertIn("vp", data)                              # viewport rect
        self.assertTrue(any(tr["p"] == "dr" for tr in data["tracks"]))  # Create -> draw-range


@unittest.skipUnless(_TOOLCHAIN and _HAVE_NUMPY, "needs Pango + latex + numpy")
class SvgAnimTextTest(unittest.TestCase):
    """Text/shapes in an animation: glyphs bake to shared `<defs>` + `<use>`, a
    Transform bakes its end shape, and default colours follow the deck foreground
    (not wanim's white, which would be invisible on a light slide)."""

    ANIM = (
        "from lemur.anim import Anim, Text, Square, Circle, Write, Create, Transform\n\n"
        "class Demo(Anim):\n"
        "    def build(self):\n"
        "        self.play(Write(Text('hi')))\n"
        "        self.next()\n"
        "        sq = Square(side=2)\n"
        "        self.play(Create(sq))\n"
        "        self.next()\n"
        "        self.play(Transform(sq, Circle(radius=1.2)))\n"
        "        self.next()\n"
    )
    DECK = "!slide Text & morph\n\n!anim\n\t!src demo.py\n"

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.mkdtemp(prefix="lemur-svganimtx-")
        with open(os.path.join(cls._tmp, "demo.py"), "w", encoding="utf-8") as fh:
            fh.write(cls.ANIM)
        src = os.path.join(cls._tmp, "deck.lmr")
        with open(src, "w", encoding="utf-8") as fh:
            fh.write(cls.DECK)
        out = os.path.join(cls._tmp, "deck.html")
        svg.build(src, out)
        with open(out, encoding="utf-8") as fh:
            cls.html = fh.read()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls._tmp, ignore_errors=True)

    def test_glyphs_bake_to_use_and_defs(self):
        # 'hi' shapes to <use> nodes referencing id-namespaced glyph <defs>.
        self.assertRegex(self.html, r'<defs><path id="ad\d+_[0-9a-f]+"')
        self.assertRegex(self.html, r'<use data-i="\d+"[^>]*href="#ad\d+_')

    def test_default_colour_follows_deck_not_white(self):
        # A plain Text must not be baked white (invisible on the light slide).
        anim = re.search(r'<g class="anim-cam".*?</g></g></g>', self.html, re.S).group(0)
        fills = re.findall(r'<use[^>]*fill="(#[0-9a-fA-F]{6})"', anim)
        self.assertTrue(fills and all(f.lower() != "#ffffff" for f in fills))

    def test_transform_bakes_end_shape(self):
        # The morph target is baked (a d-morph track drives the path node).
        m = re.search(r"data-anim='(\{.*?\})'", self.html)
        import json
        data = json.loads(m.group(1))
        self.assertTrue(any(tr["p"] == "d" for tr in data["tracks"]))


@unittest.skipUnless(_HAVE_PANGO and _HAVE_MPL, "needs Pango + matplotlib")
class SvgPlotTest(unittest.TestCase):
    """`!plot` runs a matplotlib `!src` at build time and bakes the figure to a
    self-contained SVG placed like a figure (with a caption)."""

    PLOT = (
        "import matplotlib.pyplot as plt\n\n"
        "def figure():\n"
        "    fig, ax = plt.subplots()\n"
        "    ax.plot([0, 1, 2], [0, 1, 4], label='y')\n"
        "    ax.set_xlabel('x'); ax.legend()\n"
        "    return fig\n"
    )
    DECK = "!slide A plot\n\n!plot Demo ^fig\n\t!src fig.py\n\t!caption A parabola.\n\t!width 60%\n"

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.mkdtemp(prefix="lemur-svgplot-")
        with open(os.path.join(cls._tmp, "fig.py"), "w", encoding="utf-8") as fh:
            fh.write(cls.PLOT)
        src = os.path.join(cls._tmp, "deck.lmr")
        with open(src, "w", encoding="utf-8") as fh:
            fh.write(cls.DECK)
        out = os.path.join(cls._tmp, "deck.html")
        svg.build(src, out)
        with open(out, encoding="utf-8") as fh:
            cls.html = fh.read()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls._tmp, ignore_errors=True)

    def test_figure_embedded_as_svg_data_uri(self):
        # the matplotlib figure is baked to a self-contained SVG <image>.
        self.assertIn("data:image/svg+xml;base64,", self.html)
        self.assertRegex(self.html, r"<image[^>]*href=\"data:image/svg\+xml;base64,")

    def test_caption_present(self):
        # caption text is typeset onto the slide (glyph <use>s exist for it).
        slide = self.html.split('class="slide"', 1)[1]
        self.assertIn('<use href="#g', slide)


if __name__ == "__main__":
    unittest.main()
