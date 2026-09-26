"""Unit tests for the build-time HTML emitter (lemur.emit.html): the per-node
render paths turn the neutral document AST (spec/ast.schema.json) into the slide
DOM described by the display contract. Ported from the old runtime render.test.mjs
when rendering moved from the browser to build time (Plan-DisplayModel Phase 3).
Assertions are on the emitted HTML string (the emitter is deterministic)."""
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))   # tests/python -> repo root
import lemur.emit.html as R

T = lambda v: {"type": "text", "value": v}


class TestInline(unittest.TestCase):
    def r(self, nodes, ctx=R.EMPTY_CTX):
        return R.render_inline(nodes, ctx)

    def test_strong_emph_strike_underline(self):
        h = self.r([T("a "), {"type": "strong", "content": [T("b")]},
                    {"type": "emph", "content": [T("c")]},
                    {"type": "strike", "content": [T("d")]},
                    {"type": "underline", "content": [T("e")]}])
        self.assertIn("a <strong>b</strong>", h)
        self.assertIn("<em>c</em>", h)
        self.assertIn("<s>d</s>", h)
        self.assertIn("<u>e</u>", h)

    def test_code_span_escaped_no_markup(self):
        h = self.r([{"type": "code", "value": "**argv"}])
        self.assertEqual(h, "<code>**argv</code>")
        self.assertNotIn("<strong>", h)

    def test_inline_break_is_br(self):
        h = self.r([T("top"), {"type": "break"}, T("bottom")])
        self.assertEqual(h, "top<br>bottom")

    def test_code_span_escapes_html(self):
        self.assertEqual(self.r([{"type": "code", "value": "a<b & c"}]),
                         "<code>a&lt;b &amp; c</code>")

    def test_inline_math_text_node(self):
        self.assertEqual(self.r([{"type": "math", "tex": "x^2"}]), "\\(x^2\\)")

    def test_inline_math_escapes_lt(self):
        # '<' inside TeX must be HTML-escaped so the page is valid; the browser
        # hands MathJax back the literal text
        self.assertEqual(self.r([{"type": "math", "tex": "a < b"}]),
                         "\\(a &lt; b\\)")

    def test_math_marks_reinjected(self):
        h = self.r([{"type": "math", "tex": "a + b",
                     "marks": [{"name": "s", "from": 4, "to": 5}]}])
        self.assertEqual(h, "\\(a + \\htmlClass{lmr-a-s}{b}\\)")

    def test_inject_marks_nests(self):
        self.assertEqual(
            R.inject_marks("x + y", [{"name": "a", "from": 0, "to": 5},
                                     {"name": "b", "from": 4, "to": 5}]),
            "\\htmlClass{lmr-a-a}{x + \\htmlClass{lmr-a-b}{y}}")
        self.assertEqual(R.inject_marks("x^2", None), "x^2")

    def test_link_and_mark(self):
        h = self.r([{"type": "link", "href": "#/a", "content": [T("go")]},
                    {"type": "mark", "name": "key", "content": [T("word")]}])
        self.assertIn('<a href="#/a">go</a>', h)
        self.assertIn('<span class="lmr-a-key">word</span>', h)

    def test_styled_span(self):
        h = self.r([{"type": "span", "content": [T("x")], "style": {
            "classes": ["accent", "bold", "italic"], "color": "#c0392b", "bg": "#eef"}}])
        self.assertIn('class="accent bold italic"', h)
        self.assertIn("color:#c0392b", h)
        self.assertIn("background-color:#eef", h)
        # a named mark can be styled too and keeps its anchor class
        m = self.r([{"type": "mark", "name": "k", "content": [T("y")],
                     "style": {"color": "#000"}}])
        self.assertIn('class="lmr-a-k"', m)
        self.assertIn("color:#000", m)

    def test_inline_reveal_gate(self):
        h = self.r([{"type": "mark", "name": "a", "content": [T("x")],
                     "reveal": {"spec": "2-"}},
                    {"type": "span", "content": [T("y")], "reveal": {"spec": "3"}}])
        self.assertRegex(h, r'class="lmr-a-a" data-appear="2"')   # "n-" cumulative
        self.assertRegex(h, r'<span data-when="3">y</span>')      # bounded overlay

    def test_xref_resolve_and_badref(self):
        ctx = {"ids": {"sec": True}, "bib": {}, "labels": {"sec": "The section"}}
        self.assertIn('<a href="#/sec">The section</a>',
                      self.r([{"type": "xref", "target": "sec"}], ctx))
        bad = self.r([{"type": "xref", "target": "nope"}], ctx)
        self.assertIn('class="lmr-badref"', bad)
        self.assertIn("@nope", bad)

    def test_cite_numbers_and_links(self):
        ctx = {"ids": {}, "bib": {"a": 1, "b": 2}, "labels": {}}
        h = self.r([{"type": "cite", "keys": ["a", "b"]}], ctx)
        self.assertIn('<sup class="lmr-cite">', h)
        self.assertIn('<a href="#/bib-a">1</a>', h)
        self.assertIn('<a href="#/bib-b">2</a>', h)


class TestBlocks(unittest.TestCase):
    def test_para_and_heading_levels(self):
        p = R.render_block({"type": "para",
                            "content": [T("hi "), {"type": "strong", "content": [T("x")]}]})
        self.assertTrue(p.startswith("<p>"))
        self.assertIn("<strong>x</strong>", p)
        self.assertTrue(R.render_block({"type": "heading", "level": 1,
                                        "content": [T("H")]}).startswith("<h2>"))
        self.assertTrue(R.render_block({"type": "heading", "level": 4,
                                        "content": [T("H")]}).startswith("<h5>"))

    def test_labelled_block_id(self):
        self.assertIn('id="eq1"',
                      R.render_block({"type": "math", "tex": "x", "id": "eq1"}))

    def test_math_block(self):
        d = R.render_block({"type": "math", "tex": "x^2"})
        self.assertIn('class="lmr-math"', d)
        self.assertIn("\\[x^2\\]", d)
        m = R.render_block({"type": "math", "tex": "\\sum x",
                            "marks": [{"name": "sum", "from": 0, "to": 4}]})
        self.assertIn("\\[\\htmlClass{lmr-a-sum}{\\sum} x\\]", m)

    def test_list_nested_with_gates(self):
        h = R.render_block({"type": "list", "ordered": False, "items": [
            {"content": [T("a")], "reveal": {"spec": "2-"}},
            {"content": [T("b")], "reveal": {"spec": "3"}, "sublist": {
                "type": "list", "ordered": True, "items": [{"content": [T("c")]}]}}]})
        self.assertTrue(h.startswith("<ul>"))
        self.assertIn('<li data-appear="2">a</li>', h)
        self.assertIn('<li data-when="3">b</li>', h)
        self.assertIn("<ol><li>c</li></ol>", h)

    def test_code_lines_and_highlight_map(self):
        c = R.render_block({"type": "code", "language": "python", "source": "a\nb",
                            "highlights": [{"reveal": {"spec": "1-"}, "lines": [1]}]})
        self.assertIn('class="language-python"', c)
        self.assertIn('<span class="cl" data-line="2">b</span>', c)
        self.assertIn('data-highlights="{&quot;1&quot;:[&quot;1&quot;]}"', c)

    def test_table_align_and_separator(self):
        t = R.render_block({"type": "table",
                            "columns": [{"heading": [T("N")], "align": "right"}],
                            "rows": [{"cells": [[T("1")]]},
                                     {"separator": "strong"}, {"cells": [[T("2")]]}]})
        self.assertIn('<th style="text-align:right">N</th>', t)
        self.assertIn('<tr class="lmr-sep-strong">', t)

    def test_table_noheader_omits_thead(self):
        t = R.render_block({"type": "table", "header": False,
                            "columns": [{"heading": [T("N")], "align": "left"}],
                            "rows": [{"cells": [[T("1")]]}]})
        self.assertNotIn("<thead>", t)
        self.assertNotIn("<th ", t)
        self.assertIn("<td style=\"text-align:left\">1</td>", t)

    def test_figure_single_and_multi(self):
        one = R.render_block({"type": "figure", "sources": ["a.svg"], "width": "60%"})
        self.assertIn("lmr-sized", one)
        self.assertIn("width:60%", one)
        self.assertIn('<img src="a.svg" alt="">', one)
        multi = R.render_block({"type": "figure", "sources": ["a.svg", "b.svg"],
                                "layers": [{"spec": "2-"}]})
        self.assertIn('class="lmr-overlay"', multi)
        self.assertIn('src="b.svg" alt="" data-appear="2"', multi)

    def test_annotate_reserves_geometry(self):
        a = R.render_block({"type": "annotate", "items": [
            {"mark": "s", "label": [T("sum")], "color": "#123456",
             "reveal": {"spec": "1-"}}]})
        self.assertIn("min-height:81px", a)          # 21 + 60*1
        self.assertIn('data-anchor="lmr-a-s"', a)
        self.assertIn('data-appear="1"', a)
        self.assertIn("--hl:#123456", a)

    def test_spacer(self):
        self.assertIn('class="lmr-gap"', R.render_block({"type": "spacer"}))
        self.assertIn("height:2em",
                      R.render_block({"type": "spacer", "size": "2em"}))
        fill = R.render_block({"type": "spacer", "size": "fill"})
        self.assertIn("lmr-gap-fill", fill)
        self.assertNotIn("height:", fill)

    def test_connect_carriers(self):
        c = R.render_block({"type": "connect", "links": [
            {"from": "q1", "to": "a1", "dir": "fwd", "color": "#c0392b",
             "reveal": {"spec": "1-"}},
            {"from": "a1", "to": "a2", "dir": "both", "styles": ["dashed", "thin"],
             "reveal": {"spec": "2-"}}]})
        self.assertIn('class="lmr-connects"', c)
        self.assertIn('data-from="lmr-a-q1"', c)
        self.assertIn('data-to="lmr-a-a1"', c)
        self.assertIn('data-dir="fwd"', c)
        self.assertIn("--arrow-color:#c0392b", c)
        self.assertIn('data-styles="dashed thin"', c)

    def test_env_titled_and_nested(self):
        e = R.render_block({"type": "env", "kind": "theorem",
                            "title": [T("Pythagoras")], "body": [
                                {"type": "para", "content": [T("a")]},
                                {"type": "env", "kind": "remark",
                                 "body": [{"type": "para", "content": [T("b")]}]}]})
        self.assertTrue(e.startswith("<section"))
        self.assertIn("lmr-env env-theorem", e)
        self.assertIn('<span class="lmr-env-kind">theorem</span>', e)
        self.assertIn('<span class="lmr-env-title">Pythagoras</span>', e)
        self.assertIn("env-remark", e)

    def test_env_no_title(self):
        e = R.render_block({"type": "env", "kind": "proof",
                            "body": [{"type": "para", "content": [T("x")]}]})
        self.assertNotIn("lmr-env-title", e)
        self.assertIn('<span class="lmr-env-kind">proof</span>', e)

    def test_bibliography_and_notes(self):
        b = R.render_block({"type": "bibliography", "entries": [
            {"key": "doe", "content": [T("Doe 2025")]}]},
            {"ids": {}, "bib": {"doe": 1}, "labels": {}})
        self.assertIn('<li id="bib-doe" value="1">Doe 2025</li>', b)
        n = R.render_block({"type": "notes", "body": [
            {"type": "para", "content": [T("hi")]},
            {"type": "para", "content": [T("bye")]}]})
        self.assertTrue(n.startswith('<aside class="notes">'))
        self.assertEqual(n.count("<p>"), 2)

    def test_style_block(self):
        b = R.render_block({"type": "style",
                            "style": {"classes": ["center", "frame"], "bg": "#f5f7ff"},
                            "body": [{"type": "para", "content": [T("inside")]}]})
        self.assertIn('class="lmr-style center frame"', b)
        self.assertIn("background-color:#f5f7ff", b)
        self.assertIn("<p>inside</p>", b)

    def test_columns(self):
        c = R.render_block({"type": "columns", "style": {"classes": ["boxed"]},
                            "columns": [
                                {"weight": 60, "body": [{"type": "para", "content": [T("L")]}]},
                                {"weight": 40, "style": {"classes": ["center"]},
                                 "body": [{"type": "para", "content": [T("R")]}]}]})
        self.assertIn('class="lmr-columns boxed"', c)
        self.assertIn('class="lmr-column" style="flex:60"', c)
        self.assertIn('class="lmr-column center" style="flex:40"', c)
        self.assertIn("<p>L</p>", c)

    def test_stack(self):
        s = R.render_block({"type": "stack", "layers": [
            {"reveal": {"spec": "1"}, "body": [{"type": "para", "content": [T("a")]}]},
            {"reveal": {"spec": "2-"}, "body": [{"type": "para", "content": [T("b")]}]}]})
        self.assertIn('<div class="lmr-layer" data-when="1">', s)
        self.assertIn('<div class="lmr-layer" data-when="2-">', s)


class TestDeck(unittest.TestCase):
    def test_pagination_wrappers_footer_attrs(self):
        deck = R.render_deck({
            "astVersion": 1, "meta": {},
            "presentation": {"transition": {"across": "slide", "step": "rise"}},
            "body": [
                {"type": "pagebreak", "role": "content", "id": "a",
                 "variant": ["plain"], "title": [T("T")]},
                {"type": "para", "content": [T("hi")]},
                {"type": "para", "reveal": {"spec": "2-"}, "content": [T("later")]},
                {"type": "para", "reveal": {"spec": "3"}, "content": [T("gated")]}]})
        self.assertIn('data-transition="slide"', deck.attrs)
        self.assertIn('data-step-transition="rise"', deck.attrs)
        self.assertIn('class="slide content plain" id="a"', deck.html)
        self.assertIn("<h2>T</h2>", deck.html)
        self.assertIn('<div class="lmr-step" data-appear="2">', deck.html)
        self.assertIn('<div class="lmr-when" data-when="3">', deck.html)
        self.assertIn("1 / 1", deck.html)

    def test_cover_synthesis(self):
        deck = R.render_deck({
            "astVersion": 1,
            "meta": {"title": "T", "subtitle": "S", "authors": ["A"], "affiliation": "B"},
            "presentation": {}, "body": [{"type": "pagebreak", "title": [T("One")]}]})
        self.assertIn('class="slide cover"', deck.html)
        self.assertIn("<h1>T</h1>", deck.html)
        self.assertIn('<p class="lmr-title-subtitle">S</p>', deck.html)
        self.assertIn("A · B", deck.html)      # byline "A · B"
        # the cover has no footer
        cover = deck.html[:deck.html.index("</section>") + 10]
        self.assertNotIn("lmr-footer", cover)

    def test_madewith_marks_the_first_slide_only(self):
        body = [{"type": "pagebreak", "title": [T("One")]}, {"type": "pagebreak", "title": [T("Two")]}]
        deck = R.render_deck({"astVersion": 1, "meta": {"title": "T"},
                              "presentation": {"madeWith": True}, "body": body})
        self.assertEqual(deck.html.count("lmr-madewith"), 1)
        cover = deck.html[:deck.html.index("</section>") + 10]
        self.assertIn("made with <b>lemur</b>", cover)
        self.assertIn('fill="currentColor"', cover)                     # the logo takes the text colour
        deck = R.render_deck({"astVersion": 1, "meta": {},            # no cover: the first slide
                              "presentation": {"madeWith": True}, "body": body})
        first = deck.html[:deck.html.index("</section>") + 10]
        self.assertIn("lmr-madewith", first)
        self.assertEqual(deck.html.count("lmr-madewith"), 1)

    def test_section_page_no_header_or_logo(self):
        deck = R.render_deck({
            "astVersion": 1, "meta": {},
            "presentation": {"header": [T("H")], "footer": [T("F")], "logo": "l.svg"},
            "body": [
                {"type": "pagebreak", "role": "section", "id": "s", "title": [T("Part")]},
                {"type": "pagebreak", "title": [T("Two")]},
                {"type": "pagebreak", "title": [T("Three")]}]})
        sec = deck.html[:deck.html.index("</section>")]
        self.assertIn('class="slide section"', sec)
        self.assertNotIn("lmr-header", sec)
        self.assertNotIn("lmr-logo", sec)
        self.assertIn("1 / 3", sec)


if __name__ == "__main__":
    unittest.main()
