"""Unit tests for lemur.parser covering parsing, inline rendering, tables,
fragments, includes, and error diagnostics."""

import contextlib
import io
import os
import re
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from lemur import (  # noqa: E402  (parser: .lmr -> neutral AST)
    LemurError, Line, Parser, load_lines,
    parse_cols, parse_inline,
    extract_marks, deck_to_ast, block_to_ast, parse_transition,
    parse_line_ranges, parse_ann_style, parse_connect_style, parse_style,
    split_ref, styles_from_bracket, split_row,
)
from lemur.emit.slides import (  # noqa: E402  (HTML emitter: AST -> deck folder)
    build, find_theme, load_theme, list_themes, theme_desc, resolve_theme_name,
    render_template,
)


def inline_text(nodes):
    """Flatten inline nodes to their visible text (for asserting content)."""
    out = []
    for n in nodes:
        t = n["type"]
        if t in ("text", "code"):
            out.append(n["value"])
        elif t == "math":
            out.append(n["tex"])
        elif t == "xref":
            out.append(inline_text(n["content"]) if n.get("content")
                       else "@" + n["target"])
        elif "content" in n:
            out.append(inline_text(n["content"]))
        elif "prefix" in n:
            out.append(inline_text(n["prefix"]))
    return "".join(out)


def inline_types(nodes):
    """The type of each top-level inline node (for asserting structure)."""
    return [n["type"] for n in nodes]


def paginate(body):
    """Split the flat AST body into pages at 'pagebreak' markers: each page is
    its marker fields plus the block nodes up to the next one."""
    pages, cur = [], None
    for n in body:
        if n["type"] == "pagebreak":
            cur = dict(n, nodes=[])
            pages.append(cur)
        elif cur is not None:
            cur["nodes"].append(n)
    return pages


def deck_slides(src):
    """The paginated slides (each a pagebreak marker + its blocks) of `src`."""
    return paginate(deck_to_ast(parse(src))["body"])


def slide_nodes(src):
    """The AST block-node list of the first slide of `src`."""
    return deck_slides(src)[0]["nodes"]


def _walk(nodes, fn):
    for n in nodes:
        fn(n)
        # only container nodes hold child block bodies (a figure's 'layers' are
        # reveal specs, not bodies — handled separately in reveal_specs)
        if n.get("type") == "columns":
            for col in n["columns"]:
                _walk(col["body"], fn)
        elif n.get("type") == "stack":
            for lyr in n["layers"]:
                _walk(lyr["body"], fn)


def _list_specs(node, out):
    for it in node["items"]:
        if it.get("reveal"):
            out.append(it["reveal"]["spec"])
        if it.get("sublist"):
            _list_specs(it["sublist"], out)


def reveal_specs(nodes):
    """Every reveal spec across a node list — blocks, list items, figure layers,
    annotate items and stack layers — in document order."""
    out = []

    def collect(n):
        if n.get("reveal"):
            out.append(n["reveal"]["spec"])
        t = n["type"]
        if t == "figure":
            out.extend(lyr["spec"] for lyr in n.get("layers", []))
        elif t == "annotate":
            out.extend(it["reveal"]["spec"]
                       for it in n["items"] if it.get("reveal"))
        elif t == "list":
            _list_specs(n, out)
        elif t == "stack":
            out.extend(lyr["reveal"]["spec"] for lyr in n["layers"])
    _walk(nodes, collect)
    return out


def appear_steps(nodes):
    """Cumulative activations (a reveal spec 'n-'), as sorted step numbers — the
    AST analogue of scanning the rendered slide for data-appear."""
    return sorted(int(m.group(1)) for s in reveal_specs(nodes)
                  for m in [re.match(r"^(\d+)-$", s)] if m)


def when_specs(nodes):
    """Bounded overlay specs (anything other than a cumulative 'n-')."""
    return [s for s in reveal_specs(nodes) if not re.match(r"^\d+-$", s)]


def built_index(master, **kw):
    """Build `master` to a temp folder and return the index.html string."""
    out = os.path.join(os.path.dirname(master), "_out")
    build(master, out, **kw)
    with open(os.path.join(out, "index.html")) as fh:
        return fh.read()


def parse(src: str):
    lines = [Line("test.lmr", i + 1, t)
             for i, t in enumerate(src.splitlines())]
    return Parser(lines).parse()


class TestInline(unittest.TestCase):
    """Inline markup parses to a node list (rendered to DOM by the runtime)."""

    def test_emphasis(self):
        nodes = parse_inline("a **bold** and __italic__ word", {})
        strong = [n for n in nodes if n["type"] == "strong"][0]
        em = [n for n in nodes if n["type"] == "emph"][0]
        self.assertEqual(inline_text(strong["content"]), "bold")
        self.assertEqual(inline_text(em["content"]), "italic")

    def test_nested_emphasis(self):
        nodes = parse_inline("**__bi__**", {})
        self.assertEqual(nodes[0]["type"], "strong")
        self.assertEqual(nodes[0]["content"][0]["type"], "emph")
        self.assertEqual(inline_text(nodes[0]["content"][0]["content"]), "bi")

    def test_code_span_protected(self):
        # markup inside code spans must not be interpreted
        nodes = parse_inline("use `**argv` here", {})
        code = [n for n in nodes if n["type"] == "code"][0]
        self.assertEqual(code["value"], "**argv")
        self.assertNotIn("strong", inline_types(nodes))

    def test_inline_math(self):
        nodes = parse_inline(r"sum: $\sum_{i=1}^{10}{i^2}$ done", {})
        math = [n for n in nodes if n["type"] == "math"][0]
        self.assertEqual(math["tex"], r"\sum_{i=1}^{10}{i^2}")

    def test_math_protects_emphasis(self):
        nodes = parse_inline(r"$a__b__c$", {})
        self.assertEqual(inline_types(nodes), ["math"])   # no em inside math

    def test_strikethrough(self):
        nodes = parse_inline("a ~~gone~~ b and **__~~all~~__**", {})
        strike = [n for n in nodes if n["type"] == "strike"][0]
        self.assertEqual(inline_text(strike["content"]), "gone")
        # nests inside other emphasis (bold > italic > strike)
        outer = [n for n in nodes if n["type"] == "strong"][0]
        self.assertEqual(outer["content"][0]["content"][0]["type"], "strike")

    def test_underline(self):
        # '++text++' is the underline shorthand ('{.underline}' is the fallback)
        nodes = parse_inline("plain ++under++ and `a++b` here", {})
        u = [n for n in nodes if n["type"] == "underline"][0]
        self.assertEqual(inline_text(u["content"]), "under")
        # a lone '++' inside a code span is not an underline marker
        self.assertEqual([n for n in nodes if n["type"] == "code"][0]["value"],
                         "a++b")

    def test_smart_dashes_and_ellipsis(self):
        # '--' -> en, '---' -> em (longest first), '...' -> ellipsis
        v = parse_inline("pages 3--5, wait---no, well...", {})[0]["value"]
        self.assertEqual(v, "pages 3–5, wait—no, well…")

    def test_smart_quotes(self):
        # opening vs closing by context; apostrophes and decades stay apostrophes
        v = parse_inline("she said \"it's the '80s\"", {})[0]["value"]
        self.assertEqual(v, "she said “it’s the ’80s”")

    def test_smart_typography_skips_verbatim(self):
        # dashes/quotes/ellipsis are educated only on prose runs, never inside
        # code spans or math (the invariant that keeps code samples byte-exact)
        nodes = parse_inline("run `make --all...` on $a--b$ -- ok", {})
        code = [n for n in nodes if n["type"] == "code"][0]
        math = [n for n in nodes if n["type"] == "math"][0]
        self.assertEqual(code["value"], "make --all...")   # untouched
        self.assertEqual(math["tex"], "a--b")              # untouched
        self.assertIn("– ok", nodes[-1]["value"])     # prose educated

    def test_backslash_escape(self):
        # a backslash forces the next special char literal, bypassing markup and
        # smart typography; a '\' before an ordinary char stays literal
        def text(s):
            return "".join(n["value"] for n in parse_inline(s, {})
                           if n["type"] == "text")
        # smart-typography chars: escaped -> straight, no education
        self.assertEqual(text(r'say \"hi\" and 3\--5 and dots\...'),
                         'say "hi" and 3--5 and dots...')
        # markup delimiters: escaped -> literal, no node produced
        nodes = parse_inline(r"not \*bold\* nor \`code\` nor \@ref", {})
        self.assertEqual([n["type"] for n in nodes], ["text"])
        self.assertEqual(nodes[0]["value"], "not *bold* nor `code` nor @ref")
        # a backslash before a normal char is a literal backslash
        self.assertEqual(text(r"a\b path"), r"a\b path")

    def test_text_kept_literal(self):
        # '<', '&', '>' are plain text nodes; the runtime escapes them on render
        nodes = parse_inline("a < b & c > d", {})
        self.assertEqual(inline_types(nodes), ["text"])
        self.assertEqual(nodes[0]["value"], "a < b & c > d")

    def test_url_and_mail(self):
        nodes = parse_inline("see <https://x.tld> or <a@b.tld>", {})
        links = [n for n in nodes if n["type"] == "link"]
        self.assertEqual(links[0]["href"], "https://x.tld")
        self.assertEqual(links[1]["href"], "mailto:a@b.tld")

    def test_ref_link(self):
        # an internal reference is symbolic: an xref carries the target name only,
        # resolution to a slide/anchor is the emitter's job (no #/sid here)
        refs = {"intro": ("intro-1", "Introduction", "slide")}
        nodes = parse_inline("see @intro and [here]@intro", refs)
        xrefs = [n for n in nodes if n["type"] == "xref"]
        self.assertEqual(xrefs[0]["target"], "intro")
        self.assertNotIn("content", xrefs[0])          # bare @intro: no link text
        self.assertEqual(inline_text(xrefs[1]["content"]), "here")

    def test_named_url_ref(self):
        refs = {"website": (None, "https://rochus.net", "url")}
        nodes = parse_inline("[my site]@website", refs)
        link = [n for n in nodes if n["type"] == "link"][0]
        self.assertEqual(link["href"], "https://rochus.net")
        self.assertEqual(inline_text(link["content"]), "my site")

    def test_citation(self):
        # a bibliography citation is symbolic: it carries the keys, not numbers
        refs = {"doe2025": ("refs-slide", "1", "bib"),
                "alice2024": ("refs-slide", "2", "bib")}
        nodes = parse_inline("@(doe2025, alice2024)", refs)
        cite = [n for n in nodes if n["type"] == "cite"][0]
        self.assertEqual(cite["keys"], ["doe2025", "alice2024"])

    def test_unresolved_ref(self):
        # an unknown target stays a symbolic xref; the emitter flags it
        nodes = parse_inline("@nothere", {})
        self.assertEqual(nodes[0]["type"], "xref")
        self.assertEqual(nodes[0]["target"], "nothere")

    def test_email_not_treated_as_ref(self):
        # 'mail@domain.tld' stays literal — the '@' is inside an email address
        nodes = parse_inline("write to mail@somedomain.tld please", {})
        self.assertNotIn("xref", inline_types(nodes))
        self.assertNotIn("cite", inline_types(nodes))

    def test_reference_stops_at_punctuation(self):
        # a ref/cite name is [\w-]; trailing punctuation terminates it so it
        # still resolves (regression: ':' was swallowed into the key)
        refs = {"jonas2010": ("refs", "3", "bib")}
        for s in ("see @jonas2010: nice", "cf @jonas2010. end",
                  "as in @jonas2010, again"):
            cite = [n for n in parse_inline(s, refs) if n["type"] == "cite"][0]
            self.assertEqual(cite["keys"], ["jonas2010"], s)
        # the terminating punctuation survives as ordinary text
        text = "".join(n["value"] for n in parse_inline("see @jonas2010: x", refs)
                       if n["type"] == "text")
        self.assertIn(":", text)

    def test_citation_may_abut_a_word(self):
        # 'Author@key' is a citation (not an email) — an email needs a dot-TLD
        refs = {"jonas2010": ("refs", "3", "bib")}
        cite = [n for n in parse_inline("Kording@jonas2010: nice", refs)
                if n["type"] == "cite"][0]
        self.assertEqual(cite["keys"], ["jonas2010"])
        # but a real email (word@host.tld) still stays literal
        self.assertNotIn("cite",
                         inline_types(parse_inline("me@work.com now", refs)))


class TestStructure(unittest.TestCase):
    def test_slides(self):
        deck = parse("!slide A\ntext\n!slide B\nmore")
        self.assertEqual(len(deck.groups), 2)
        self.assertEqual(deck.groups[1][0].title, "B")

    def test_removed_directives_error(self):
        # !math, !template and !subslide were removed (vestigial)
        for src in ("!math mathjax\n!slide A\nx",
                    "!template dark\n!slide A\nx",
                    "!slide A\n!subslide B\ny"):
            with self.assertRaises(LemurError):
                parse(src)

    def test_slide_style_classes(self):
        deck = parse("!slide[.hero .plain] My Slide ^ref\nx")
        s = deck.groups[0][0]
        self.assertEqual(s.title, "My Slide")
        self.assertEqual(s.ref, "ref")
        self.assertEqual(s.styles, ["hero", "plain"])
        # the styles flow into the pagebreak as neutral variant tokens
        pb = paginate(deck_to_ast(deck)["body"])[0]
        self.assertEqual(pb.get("role", "content"), "content")
        self.assertEqual(pb["variant"], ["hero", "plain"])
        self.assertEqual(pb["id"], "ref")

    def test_slide_title_may_start_with_bracket(self):
        # a space after the directive means no option bracket binds, so a title
        # that itself starts with '[' is unambiguous
        deck = parse("!slide [draft] Work in progress\nx")
        s = deck.groups[0][0]
        self.assertEqual(s.title, "[draft] Work in progress")
        self.assertEqual(s.styles, [])

    def test_section_style_classes(self):
        deck = parse("#[.center] Outlook\ntext")
        self.assertEqual(deck.groups[0][0].styles, ["center"])

    def test_section_heading(self):
        deck = parse("# Part One ^p1\n!slide X\ny")
        self.assertEqual(deck.groups[0][0].kind, "section")
        self.assertIn("p1", deck.refs)

    def test_content_outside_slide_fails(self):
        with self.assertRaises(LemurError):
            parse("just some text")

    def test_pause_steps(self):
        deck = parse("!slide A\none\n\n!pause\n\ntwo\n\n!pause\n\nthree")
        steps = [b.step for b in deck.groups[0][0].blocks]
        self.assertEqual(steps, [0, 1, 2])

    def test_meta(self):
        deck = parse("!title My Talk\n!aspect 4:3\n!slide A\nx")
        self.assertEqual(deck.meta["title"], "My Talk")
        self.assertEqual(deck.meta["aspect"], "4:3")

    def test_split_ref(self):
        self.assertEqual(split_ref("Some title ^ref"), ("Some title", "ref"))
        self.assertEqual(split_ref("No ref here"), ("No ref here", None))
        self.assertEqual(split_ref("^only"), ("", "only"))

    def test_styles_from_bracket(self):
        self.assertEqual(styles_from_bracket("[.hero]"), ["hero"])
        self.assertEqual(styles_from_bracket("[.hero .plain]"),
                         ["hero", "plain"])
        self.assertEqual(styles_from_bracket(None), [])
        self.assertEqual(styles_from_bracket("[]"), [])
        # non-class tokens are ignored; a '<...>' overlay bracket yields none
        self.assertEqual(styles_from_bracket("[.a b .c]"), ["a", "c"])
        self.assertEqual(styles_from_bracket("<2->"), [])


class TestBlocks(unittest.TestCase):
    def test_code_block(self):
        deck = parse("!slide A\n:: cpp ^cref\n\tint x;\n\tint y;\n")
        blk = deck.groups[0][0].blocks[0]
        self.assertEqual(blk.kind, "code")
        self.assertEqual(blk.data["lang"], "cpp")
        self.assertEqual(blk.data["text"], "int x;\nint y;")
        self.assertIn("cref", deck.refs)

    def test_parse_line_ranges(self):
        self.assertEqual(parse_line_ranges("1"), [1])
        self.assertEqual(parse_line_ranges("4-6"), [4, 5, 6])
        self.assertEqual(parse_line_ranges("3,7"), [3, 7])
        self.assertEqual(parse_line_ranges("1-2,5"), [1, 2, 5])
        self.assertEqual(parse_line_ranges("x"), [])  # invalid skipped

    def test_code_block_keeps_blank_lines(self):
        deck = parse("!slide A\n::\n\tline1\n\n\tline2\n")
        blk = deck.groups[0][0].blocks[0]
        self.assertEqual(blk.data["text"], "line1\n\nline2")

    def test_code_block_source_is_byte_exact(self):
        # a block's source never passes through the inline parser, so smart
        # typography (dashes/quotes/ellipsis) leaves code samples untouched
        deck = parse("!slide A\n:: sh\n\tgrep --color 'x' ... # \"done\"\n")
        blk = deck.groups[0][0].blocks[0]
        self.assertEqual(blk.data["text"], "grep --color 'x' ... # \"done\"")

    def test_math_block(self):
        deck = parse("!slide A\n:: math\n\t\\sum_i x_i\n")
        blk = deck.groups[0][0].blocks[0]
        self.assertEqual(blk.kind, "math")
        self.assertEqual(blk.data["tex"], "\\sum_i x_i")

    def test_list_nesting_and_fragments(self):
        deck = parse("!slide A\n- one\n- two\n\t- nested\n+ frag\n")
        blk = deck.groups[0][0].blocks[0]
        self.assertEqual(blk.kind, "list")
        ws = [i[0] for i in blk.data["items"]]
        self.assertTrue(ws[2].startswith(ws[0]) and len(ws[2]) > len(ws[0]))
        self.assertTrue(blk.data["items"][3][3])  # '+' item is a fragment

    def test_image_multi_src(self):
        deck = parse("!slide A\n!img Fig ^f1\n!src a.svg\n!src b.svg\n"
                     "!caption cap\n!width 80%\n")
        blk = deck.groups[0][0].blocks[0]
        self.assertEqual(blk.data["srcs"], ["a.svg", "b.svg"])
        self.assertEqual(blk.data["width"], "80%")

    def test_image_width_sized_multi(self):
        # !width carries the width; single- and multi-layer figures are identical
        # (the emitter derives 'sized' from the presence of width/height)
        deck = parse("!slide A\n!img\n!src a.svg\n!src b.svg\n!width 85%\n")
        node = block_to_ast(deck.groups[0][0].blocks[0], {})
        self.assertEqual(node["type"], "figure")
        self.assertEqual(node["width"], "85%")
        self.assertEqual(node["sources"], ["a.svg", "b.svg"])
        self.assertEqual([l["spec"] for l in node["layers"]], ["1-"])  # one layer

    def test_image_width_sized_single(self):
        deck = parse("!slide A\n!img\n!src a.svg\n!width 60%\n")
        node = block_to_ast(deck.groups[0][0].blocks[0], {})
        self.assertEqual(node["width"], "60%")

    def test_unsized_image_is_not_sized(self):
        deck = parse("!slide A\n!img\n!src a.svg\n")
        node = block_to_ast(deck.groups[0][0].blocks[0], {})
        self.assertNotIn("width", node)
        self.assertNotIn("layers", node)

    def test_image_without_src_fails(self):
        with self.assertRaises(LemurError):
            parse("!slide A\n!img broken\n\nnext paragraph")

    def test_notes(self):
        deck = parse("!slide A\ntext\n!notes\n\tremember the joke\n")
        kinds = [b.kind for b in deck.groups[0][0].blocks]
        self.assertIn("notes", kinds)

    def test_bibliography(self):
        deck = parse("!slide Refs\n^doe2025: Doe, 2025.\n"
                     "^alice2024: Alice, 2024.\n^web: <https://x.tld>\n")
        self.assertEqual(deck.refs["doe2025"][1], "1")
        self.assertEqual(deck.refs["alice2024"][1], "2")
        self.assertEqual(deck.refs["web"][2], "url")


class TestColumns(unittest.TestCase):
    """!columns / !column layout (item 5): side-by-side content with the
    per-slide step counter flowing across columns."""

    def test_columns_parse_and_widths(self):
        # nested indentation: !columns -> tab -> !column -> tab -> content
        deck = parse("!slide C\n!columns[60,40]\n\t!column\n\t\tleft\n\t\t!pause\n"
                     "\t\tleft2\n\t!column\n\t\tright\n")
        cb = [b for b in deck.groups[0][0].blocks if b.kind == "columns"][0]
        self.assertEqual(cb.data["widths"], [60.0, 40.0])
        self.assertEqual(len(cb.data["columns"]), 2)
        # step flows across columns: left2 at step 1, right also at step 1
        self.assertEqual([bl.step for bl in cb.data["columns"][0]["blocks"]],
                         [0, 1])
        self.assertEqual([bl.step for bl in cb.data["columns"][1]["blocks"]],
                         [1])

    def test_columns_in_ast(self):
        # columns recurse into structured child nodes in the AST (the browser
        # builds the .lmr-columns/.lmr-column DOM from it)
        deck = parse("!slide C\n!columns[60,40]\n\t!column\n\t\ta\n"
                     "\t!column\n\t\tb\n")
        node = block_to_ast(deck.groups[0][0].blocks[0], {})
        self.assertEqual(node["type"], "columns")
        self.assertEqual([c["weight"] for c in node["columns"]], [60.0, 40.0])
        self.assertEqual(inline_text(node["columns"][0]["body"][0]["content"]), "a")
        self.assertEqual(inline_text(node["columns"][1]["body"][0]["content"]), "b")

    def test_columns_default_equal_width_in_ast(self):
        deck = parse("!slide C\n!columns\n\t!column\n\t\ta\n\t!column\n\t\tb\n")
        node = block_to_ast(deck.groups[0][0].blocks[0], {})
        self.assertEqual([c["weight"] for c in node["columns"]], [1, 1])  # equal
        self.assertEqual(len(node["columns"]), 2)

    def test_column_alignment_is_a_style_class(self):
        deck = parse("!slide C\n!columns\n\t!column\n\t\ta\n"
                     "\t!column[.center]\n\t\tb\n\t!column[.bottom]\n\t\tc\n")
        node = block_to_ast(deck.groups[0][0].blocks[0], {})
        # valign is now a built-in style class; a plain '!column' has none
        self.assertNotIn("style", node["columns"][0])
        self.assertEqual(node["columns"][1]["style"], {"classes": ["center"]})
        self.assertEqual(node["columns"][2]["style"], {"classes": ["bottom"]})

    def test_columns_widths_and_style_in_bracket(self):
        deck = parse("!slide C\n!columns[60 40 .boxed]\n\t!column\n\t\ta\n"
                     "\t!column\n\t\tb\n")
        node = block_to_ast(deck.groups[0][0].blocks[0], {})
        self.assertEqual([c["weight"] for c in node["columns"]], [60.0, 40.0])
        self.assertEqual(node["style"], {"classes": ["boxed"]})

    def test_column_outside_columns_fails(self):
        with self.assertRaises(LemurError):
            parse("!slide C\n!column\ntext\n")

    def test_bare_options_are_rejected(self):
        # the uniformity rule: widths and alignment go in the bracket, not bare
        for bad in ("!slide C\n!columns 60,40\n\t!column\n\t\tx\n",
                    "!slide C\n!columns[50,50]\n\t!column center\n\t\tx\n"):
            with self.assertRaises(LemurError) as cm:
                parse(bad)
            self.assertIn("bracket", str(cm.exception))

    def test_dedent_ends_columns(self):
        # a dedent to the !columns indent ends the block; no !endcolumns needed
        deck = parse("!slide C\n!columns\n\t!column\n\t\tin col\n"
                     "back at slide level\n")
        blocks = deck.groups[0][0].blocks
        self.assertEqual(blocks[0].kind, "columns")
        self.assertEqual(blocks[1].kind, "para")
        self.assertIn("back at slide level", blocks[1].data["text"])
        # 'in col' stayed inside the column
        self.assertEqual(
            blocks[0].data["columns"][0]["blocks"][0].data["text"], "in col")

    def test_columns_do_not_cross_slides(self):
        deck = parse("!slide A\n!columns\n\t!column\n\t\tx\n!slide B\ny\n")
        # '!slide B' dedents to indent 0, ending the columns; 'y' is slide B
        self.assertEqual(deck.groups[1][0].blocks[0].data["text"], "y")


class TestContainerNesting(unittest.TestCase):
    """Columns / stacks / environments all nest through one machinery: a stack
    in a column, columns in a layer, columns in a column, etc. Regression for
    the old single-slot container tracking, which broke every nested layout."""

    def test_stack_inside_a_column(self):
        # a fixed 2-column layout where one column's content toggles per step
        col = slide_nodes(
            "!slide A\n!columns[50 50]\n\t!column\n\t\tfixed\n"
            "\t!column\n\t\t!stack\n\t\t\t!layer<1>\n\t\t\t\tv1\n"
            "\t\t\t!layer<2>\n\t\t\t\tv2\n")[0]
        self.assertEqual(col["type"], "columns")
        right = col["columns"][1]["body"]
        self.assertEqual(right[0]["type"], "stack")
        self.assertEqual([l["reveal"]["spec"] for l in right[0]["layers"]],
                         ["1", "2"])
        self.assertEqual(inline_text(right[0]["layers"][0]["body"][0]["content"]),
                         "v1")

    def test_columns_inside_a_layer(self):
        # each layer is a whole column layout, toggled per step (the layout that
        # motivated the refactor)
        stack = slide_nodes(
            "!slide B\n!stack\n\t!layer<1>\n\t\t!columns[50 50]\n"
            "\t\t\t!column\n\t\t\t\tL1\n\t\t\t!column\n\t\t\t\tR1\n"
            "\t!layer<2->\n\t\t!columns[30 70]\n\t\t\t!column\n\t\t\t\tL2\n"
            "\t\t\t!column\n\t\t\t\tR2\n")[0]
        self.assertEqual(stack["type"], "stack")
        c1, c2 = stack["layers"][0]["body"][0], stack["layers"][1]["body"][0]
        self.assertEqual([c["weight"] for c in c1["columns"]], [50.0, 50.0])
        self.assertEqual([c["weight"] for c in c2["columns"]], [30.0, 70.0])
        self.assertEqual(inline_text(c1["columns"][0]["body"][0]["content"]), "L1")

    def test_columns_nested_in_a_column(self):
        cols = slide_nodes(
            "!slide N\n!columns\n\t!column\n\t\touterL\n\t\t!columns\n"
            "\t\t\t!column\n\t\t\t\tin1\n\t\t\t!column\n\t\t\t\tin2\n"
            "\t!column\n\t\touterR\n")[0]
        left = cols["columns"][0]["body"]
        self.assertEqual(inline_text(left[0]["content"]), "outerL")
        inner = left[1]
        self.assertEqual(inner["type"], "columns")
        self.assertEqual(inline_text(inner["columns"][1]["body"][0]["content"]), "in2")
        # the outer columns resumes after the inner one closes
        self.assertEqual(inline_text(cols["columns"][1]["body"][0]["content"]),
                         "outerR")

    def test_stack_nested_in_a_layer(self):
        outer = slide_nodes(
            "!slide D\n!stack\n\t!layer<1>\n\t\touter\n\t\t!stack\n"
            "\t\t\t!layer<1>\n\t\t\t\tinner\n")[0]
        self.assertEqual(outer["type"], "stack")
        body = outer["layers"][0]["body"]
        # the inner stack nests in the layer, not as a slide-level sibling
        self.assertEqual([b["type"] for b in body], ["para", "stack"])
        self.assertEqual(inline_text(body[1]["layers"][0]["body"][0]["content"]),
                         "inner")

    def test_stack_inside_environment(self):
        env = slide_nodes(
            "!slide E\n!theorem T\n\t!stack\n\t\t!layer<1>\n\t\t\tx\n")[0]
        self.assertEqual(env["type"], "env")
        self.assertEqual(env["body"][0]["type"], "stack")

    def test_step_counter_flows_into_nested_container(self):
        # a '!pause' inside a nested column still advances the slide-wide step
        deck = parse("!slide S\n!columns\n\t!column\n\t\t!stack\n"
                     "\t\t\t!layer<1>\n\t\t\t\ta\n\t\t\t\t!pause\n\t\t\t\tb\n")
        cols = deck.groups[0][0].blocks[0]
        layer = cols.data["columns"][0]["blocks"][0].data["layers"][0]
        self.assertEqual([bl.step for bl in layer["blocks"]], [0, 1])

    def test_content_directly_in_columns_errors(self):
        with self.assertRaises(LemurError) as cm:
            parse("!slide S\n!columns\n\tloose text\n")
        self.assertIn("column", str(cm.exception))

    def test_content_directly_in_stack_errors(self):
        with self.assertRaises(LemurError) as cm:
            parse("!slide S\n!stack\n\tloose text\n")
        self.assertIn("layer", str(cm.exception))


class TestTables(unittest.TestCase):
    def test_parse_cols_mixed_separators(self):
        cols, seps = parse_cols("First, Second; Third | Fourth",
                                Line("t", 1, ""))
        self.assertEqual([c["name"] for c in cols],
                         ["First", "Second", "Third", "Fourth"])
        self.assertEqual(seps, [",", ";", "|"])

    def test_parse_cols_quoted_and_aligned(self):
        cols, seps = parse_cols(
            'Name[l], "Long, header \\" x"[r] | C[c]', Line("t", 1, ""))
        self.assertEqual(cols[1]["name"], 'Long, header " x')
        self.assertEqual(cols[1]["align"], "r")
        self.assertEqual(cols[2]["align"], "c")
        self.assertEqual(seps, [",", "|"])

    def test_split_row_follows_separator_sequence(self):
        cells = split_row("a, b; c | d", [",", ";", "|"], Line("t", 1, ""))
        self.assertEqual(cells, ["a", "b", "c", "d"])

    def test_full_table(self):
        src = ("!slide T\n"
               "!table my-table ^tref\n"
               "!cols Name, Age[r], Country[c] | X\n"
               "!caption a caption spanning\n"
               "lines\n"
               "\n"
               "\tAlice , 30 , USA | yes\n"
               "\t===\n"
               "\tBob , 25 , CA | no\n"
               "\t---\n"
               "\tSteve , 27 , DK | yes\n")
        deck = parse(src)
        blk = deck.groups[0][0].blocks[0]
        self.assertEqual(blk.kind, "table")
        self.assertEqual(blk.data["caption"], "a caption spanning lines")
        rows = blk.data["rows"]
        self.assertEqual(rows[0], ["Alice", "30", "USA", "yes"])
        self.assertEqual(rows[1], "sep-strong")
        self.assertEqual(rows[3], "sep-light")

    def test_invalid_alignment(self):
        with self.assertRaises(LemurError):
            parse_cols("A[x]", Line("t", 1, ""))

    def test_parse_cols_any_punctuation_separator(self):
        # the separator is the author's choice: '&' (and any punctuation) works
        cols, seps = parse_cols("A & B & C", Line("t", 1, ""))
        self.assertEqual([c["name"] for c in cols], ["A", "B", "C"])
        self.assertEqual(seps, ["&", "&"])

    def test_parse_cols_punctuation_in_name_needs_quotes(self):
        # unquoted punctuation now splits; quote a header that must contain it
        cols, _ = parse_cols('"P(x)"[c] & Q', Line("t", 1, ""))
        self.assertEqual([c["name"] for c in cols], ["P(x)", "Q"])

    def test_ampersand_row_split(self):
        rows = slide_nodes("!slide T\n!table\n!cols A & B\n\n\tx & y\n")[0]["rows"]
        self.assertEqual(inline_text(rows[0]["cells"][0]), "x")
        self.assertEqual(inline_text(rows[0]["cells"][1]), "y")

    def test_noheader_flag(self):
        t = slide_nodes("!slide T\n!table\n!cols A, B\n!noheader\n\n\tx, y\n")[0]
        self.assertEqual(t["header"], False)
        self.assertEqual(len(t["columns"]), 2)      # cols still declared

    def test_header_shown_by_default(self):
        t = slide_nodes("!slide T\n!table\n!cols A, B\n\n\tx, y\n")[0]
        self.assertNotIn("header", t)               # default (shown) => omitted

    def test_manual_newline_in_cell(self):
        cell = slide_nodes(
            "!slide T\n!table\n!cols A\n\n\ttop \\n bottom\n")[0]["rows"][0]["cells"][0]
        self.assertEqual([n["type"] for n in cell], ["text", "break", "text"])


class TestIncludes(unittest.TestCase):
    def test_include_and_compile(self):
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "part.lmr"), "w") as fh:
                fh.write("!slide Included\nhello from part\n")
            master = os.path.join(d, "master.lmr")
            with open(master, "w") as fh:
                fh.write("!title T\n!slide First\nx\n!include part.lmr\n")
            html_doc = built_index(master)
            self.assertIn("hello from part", html_doc)   # in the embedded AST
            self.assertIn('class="deck"', html_doc)
            self.assertIn("runtime.js", html_doc)

    def test_circular_include_detected(self):
        with tempfile.TemporaryDirectory() as d:
            a, b = os.path.join(d, "a.lmr"), os.path.join(d, "b.lmr")
            with open(a, "w") as fh:
                fh.write("!include b.lmr\n")
            with open(b, "w") as fh:
                fh.write("!include a.lmr\n")
            with self.assertRaises(LemurError):
                load_lines(a)

    def test_missing_include(self):
        with tempfile.TemporaryDirectory() as d:
            master = os.path.join(d, "m.lmr")
            with open(master, "w") as fh:
                fh.write("!include nope.lmr\n")
            with self.assertRaises(LemurError):
                load_lines(master)


class TestAnnotations(unittest.TestCase):
    def test_extract_marks_basic(self):
        # marks are stripped to *raw* TeX + char spans; no MathJax macros leak
        tex, marks = extract_marks(r"\mk{sum}{\sum_i x_i} + c")
        self.assertEqual(tex, r"\sum_i x_i + c")
        self.assertEqual(marks, [{"name": "sum", "from": 0, "to": 10}])

    def test_extract_marks_nested_braces(self):
        tex, marks = extract_marks(r"\mk{s}{\sum_{i=1}^{N}{x_i}}")
        self.assertEqual(tex, r"\sum_{i=1}^{N}{x_i}")
        self.assertEqual(marks, [{"name": "s", "from": 0, "to": 19}])

    def test_extract_marks_nested(self):
        # a mark inside a mark: both spans point into the same raw TeX
        tex, marks = extract_marks(r"\mk{a}{x + \mk{b}{y}}")
        self.assertEqual(tex, "x + y")
        self.assertEqual(marks, [{"name": "a", "from": 0, "to": 5},
                                 {"name": "b", "from": 4, "to": 5}])

    def test_extract_marks_escaped_braces(self):
        tex, marks = extract_marks(r"\mk{s}{\{x \mid y\}}")
        self.assertEqual(tex, r"\{x \mid y\}")
        self.assertEqual(marks, [{"name": "s", "from": 0, "to": 12}])

    def test_extract_marks_errors(self):
        for bad in (r"\mk{unclosed", r"\mk{n}nobrace", r"\mk{n}{unbal",
                    r"\mk{bad name}{x}"):
            with self.assertRaises(ValueError):
                extract_marks(bad)

    def test_math_block_records_marks(self):
        deck = parse("!slide A\n:: math\n\t\\mk{s}{\\sum} x\n")
        blk = deck.groups[0][0].blocks[0]
        self.assertEqual(blk.data["tex"], r"\sum x")   # raw TeX, mark stripped
        self.assertEqual(blk.data["marks"], [{"name": "s", "from": 0, "to": 4}])

    def test_math_block_mark_error_is_located(self):
        with self.assertRaises(LemurError) as cm:
            parse("!slide A\n:: math\n\t\\mk{s}{\\sum\n")
        self.assertIn("test.lmr:2", str(cm.exception))

    def test_inline_math_records_marks(self):
        nodes = parse_inline(r"$\mk{s}{x}$", {})
        self.assertEqual(nodes[0]["tex"], "x")        # raw TeX
        self.assertEqual(nodes[0]["marks"], [{"name": "s", "from": 0, "to": 1}])

    def test_annotate_parsing_and_rendering(self):
        deck = parse("!slide A\n:: math\n\t\\mk{s}{\\sum}\n\n!annotate\n"
                     "\ts[#123456]: the sum\n\tother: no color given\n")
        blk = deck.groups[0][0].blocks[1]
        self.assertEqual(blk.kind, "annotate")
        self.assertEqual(blk.data["items"][0]["color"], "#123456")
        self.assertIsNone(blk.data["items"][1]["color"])
        # the annotate node carries one item per named mark with its colour,
        # reveal and label; no geometry (the emitter draws the callouts)
        node = block_to_ast(blk, {})
        items = node["items"]
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0]["mark"], "s")
        self.assertEqual(items[0]["color"], "#123456")
        self.assertEqual(inline_text(items[0]["label"]), "the sum")
        self.assertEqual([it["reveal"]["spec"] for it in items], ["1-", "2-"])
        self.assertNotIn("height", node)             # no baked geometry
        # palette fallback colours the second (uncolored) item
        self.assertIn("color", items[1])

    def test_annotate_without_body_fails(self):
        with self.assertRaises(LemurError):
            parse("!slide A\n!annotate\n\nnext")

    def test_annotate_bad_line_fails(self):
        with self.assertRaises(LemurError):
            parse("!slide A\n!annotate\n\t???: nope\n")

    def test_code_line_highlight(self):
        # each '|'-group is a step; the code node carries the lines and a
        # step->lines map (string values, matching the runtime's data-line)
        deck = parse("!slide A\n:: python[1|3-4] ^r\n\tx = 1\n\ty = 2\n")
        blk = deck.groups[0][0].blocks[0]
        self.assertEqual(blk.data["lines"], "1|3-4")
        self.assertEqual(blk.data["highlights"], {1: [1], 2: [3, 4]})
        node = block_to_ast(blk, {})
        self.assertEqual(node["language"], "python")
        self.assertEqual(node["source"], "x = 1\ny = 2")   # raw source, not split
        # highlight groups: a reveal spec ('from step n') + the emphasised lines
        self.assertEqual(node["highlights"], [
            {"reveal": {"spec": "1-"}, "lines": [1]},
            {"reveal": {"spec": "2-"}, "lines": [3, 4]}])

    def test_code_without_line_spec_has_no_highlights(self):
        deck = parse("!slide A\n:: python\n\tx = 1\n")
        node = block_to_ast(deck.groups[0][0].blocks[0], {})
        self.assertNotIn("highlights", node)
        self.assertEqual(node["source"], "x = 1")

    def test_code_no_lang(self):
        deck = parse("!slide A\n::\n\tplain text\n")
        node = block_to_ast(deck.groups[0][0].blocks[0], {})
        self.assertNotIn("language", node)


class TestMathMarks(unittest.TestCase):
    """Step 0: math marks are neutral — the AST carries raw TeX plus char-span
    marks; the DOM bridge injects the MathJax class, so no macros leak here.
    Annotate declares the step + color that decorate each mark."""

    def test_display_math_records_marks(self):
        deck = parse("!slide A\n:: math\n\t\\mk{sum}{\\sum_i x_i}\n")
        blk = deck.groups[0][0].blocks[0]
        self.assertEqual(blk.data["tex"], r"\sum_i x_i")   # raw, no macros
        self.assertEqual(blk.data["marks"], [{"name": "sum", "from": 0,
                                              "to": 10}])
        # block_to_ast carries the marks onto the neutral node
        node = block_to_ast(blk, {})
        self.assertEqual(node["marks"], [{"name": "sum", "from": 0, "to": 10}])

    def test_two_equations_record_their_own_marks(self):
        deck = parse("!slide A\n:: math\n\t\\mk{a}{x}\n\n:: math\n\t\\mk{b}{y}\n")
        b0 = deck.groups[0][0].blocks[0]
        b1 = deck.groups[0][0].blocks[1]
        self.assertEqual(b0.data["marks"][0]["name"], "a")
        self.assertEqual(b1.data["marks"][0]["name"], "b")

    def test_math_without_marks_has_no_marks_key(self):
        deck = parse("!slide A\n:: math\n\tx + y\n")
        blk = deck.groups[0][0].blocks[0]
        self.assertEqual(blk.data["tex"], "x + y")
        self.assertNotIn("marks", blk.data)
        self.assertNotIn("marks", block_to_ast(blk, {}))

    def test_inline_math_records_marks(self):
        nodes = parse_inline(r"$\mk{s}{x}$", {})
        self.assertEqual(nodes[0]["tex"], "x")
        self.assertEqual(nodes[0]["marks"], [{"name": "s", "from": 0, "to": 1}])

    def test_same_name_across_slides_is_allowed(self):
        # marks are scoped per slide, so reusing a name on a later slide is fine
        deck = parse("!slide A\n:: math\n\t\\mk{sum}{x}\n"
                     "!slide B\n:: math\n\t\\mk{sum}{y}\n")
        self.assertEqual(deck.groups[0][0].blocks[0].data["marks"][0]["name"],
                         "sum")
        self.assertEqual(deck.groups[1][0].blocks[0].data["marks"][0]["name"],
                         "sum")

    def test_duplicate_mark_on_one_slide_groups_and_warns(self):
        # reusing '\mk{sum}' on a slide is a *group*: both marks are kept (they
        # share a class -> same colour, fanned-out arrows) and a weak typo guard
        # is emitted to stderr rather than failing the build
        import io, contextlib
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            deck = parse("!slide A\n:: math\n\t\\mk{sum}{a} + \\mk{sum}{b}\n")
        marks = deck.groups[0][0].blocks[0].data["marks"]
        self.assertEqual([m["name"] for m in marks], ["sum", "sum"])
        self.assertIn("reused", err.getvalue())
        self.assertIn("sum", err.getvalue())

    def test_annotate_steps_and_colors(self):
        deck = parse("!slide A\n:: math\n\t\\mk{p}{a}\\mk{q}{b}\n\n!annotate\n"
                     "\tp: first\n\tq[#111222]: second\n")
        items = deck.groups[0][0].blocks[1].data["items"]
        self.assertEqual([it["step"] for it in items], [1, 2])
        node = block_to_ast(deck.groups[0][0].blocks[1], {})
        self.assertEqual([it["mark"] for it in node["items"]], ["p", "q"])
        self.assertEqual(node["items"][1]["color"], "#111222")  # explicit for q

    def test_prose_mark_becomes_node(self):
        nodes = parse_inline(r"the [important **word**]^key here", {})
        mark = [n for n in nodes if n["type"] == "mark"][0]
        self.assertEqual(mark["name"], "key")
        # inline markup inside the mark still parses
        self.assertIn("strong", inline_types(mark["content"]))

    def test_parse_ann_style(self):
        # dotted style names, '#' colour — the same vocabulary as a span
        self.assertEqual(parse_ann_style("#c00"), ("#c00", []))
        self.assertEqual(parse_ann_style(".bold"), (None, ["bold"]))
        self.assertEqual(parse_ann_style("#c00 .bold"), ("#c00", ["bold"]))
        self.assertEqual(parse_ann_style(".bold .italic"),
                         (None, ["bold", "italic"]))
        self.assertEqual(parse_ann_style(None), (None, []))

    def test_annotate_pure_emphasis(self):
        # a label-less line with a style class emphasises without coloring or
        # an arrow (item 4)
        deck = parse("!slide A\ntext [word]^k here\n\n"
                     "!annotate\n\tk[.bold]:\n")
        blk = deck.groups[0][0].blocks[1]
        self.assertEqual(blk.data["items"][0]["styles"], ["bold"])
        self.assertIsNone(blk.data["items"][0]["color"])
        node = block_to_ast(blk, {})
        self.assertEqual(node["items"][0]["emphasis"], ["bold"])
        self.assertNotIn("color", node["items"][0])   # no color for pure bold
        self.assertNotIn("label", node["items"][0])    # label-less item

    def test_math_and_prose_marks_coexist(self):
        # a math mark ('\mk' inside $...$) and a prose mark ('[..]^name') on the
        # same run are handled by their own paths and both stay neutral
        nodes = parse_inline(r"$\mk{m}{x}$ and [y]^p", {})
        self.assertEqual(nodes[0]["tex"], "x")               # raw math TeX
        self.assertEqual(nodes[0]["marks"][0]["name"], "m")  # math mark
        mark = [n for n in nodes if n["type"] == "mark"][0]
        self.assertEqual(mark["name"], "p")                  # prose mark node


class TestStyling(unittest.TestCase):
    """Inline '{style}' attributes and '!style'/'!columns'/'!column' containers
    carry a neutral style. One rule everywhere: '.name' = a style class,
    '#rrggbb' = colour, 'bg:…' = background. Names and hints, not css."""

    def test_parse_style(self):
        self.assertEqual(parse_style("#c0392b"), {"color": "#c0392b"})
        self.assertEqual(parse_style(".accent"), {"classes": ["accent"]})
        # emphasis is just a dotted style name now (no special 'bold' keyword)
        self.assertEqual(parse_style(".bold .italic"),
                         {"classes": ["bold", "italic"]})
        self.assertEqual(parse_style("bg:#f5f7ff"), {"bg": "#f5f7ff"})
        self.assertEqual(
            parse_style(".panel #c00 bg:eef .bold"),
            {"classes": ["panel", "bold"], "color": "#c00", "bg": "eef"})
        self.assertEqual(parse_style(""), {})

    def test_inline_styled_span(self):
        nodes = parse_inline("a [red]{#c0392b .bold} word", {})
        span = [n for n in nodes if n["type"] == "span"][0]
        self.assertEqual(inline_text(span["content"]), "red")
        self.assertEqual(span["style"], {"color": "#c0392b",
                                         "classes": ["bold"]})

    def test_style_composes_with_mark_and_reveal(self):
        nodes = parse_inline("[key]{.accent}^m<2->", {})
        self.assertEqual(nodes[0]["type"], "mark")
        self.assertEqual(nodes[0]["name"], "m")
        self.assertEqual(nodes[0]["style"], {"classes": ["accent"]})
        self.assertEqual(nodes[0]["reveal"], {"spec": "2-"})

    def test_plain_brackets_still_literal(self):
        # '{}' with nothing usable, and no ^/</@ suffix -> literal text
        nodes = parse_inline("see [x]{ } later", {})
        self.assertEqual(inline_types(nodes), ["text"])
        self.assertIn("[x]", nodes[0]["value"])

    def test_style_block_parse_and_ast(self):
        deck = parse("!slide S\n!style[.center .frame bg:#f5f7ff] ^b\n"
                     "\tinside\n\n\t:: math\n\t\tx=1\n")
        blk = deck.groups[0][0].blocks[0]
        self.assertEqual(blk.kind, "style")
        node = block_to_ast(blk, {})
        self.assertEqual(node["type"], "style")
        self.assertEqual(node["style"],
                         {"classes": ["center", "frame"], "bg": "#f5f7ff"})
        self.assertEqual(node["id"], "b")
        self.assertEqual([b["type"] for b in node["body"]], ["para", "math"])

    def test_style_block_without_style(self):
        deck = parse("!slide S\n!style\n\tjust grouped\n")
        node = block_to_ast(deck.groups[0][0].blocks[0], {})
        self.assertNotIn("style", node)
        self.assertEqual(node["body"][0]["type"], "para")

    def test_style_block_nests_and_reveals(self):
        deck = parse("!slide S\n!when<2->\n\t!style[.frame]\n\t\tgated panel\n")
        node = block_to_ast(deck.groups[0][0].blocks[0], {})
        self.assertEqual(node["type"], "style")
        self.assertEqual(node["reveal"], {"spec": "2-"})


class TestInlineReveal(unittest.TestCase):
    """A '[content]' span may carry '^name' (a mark) and/or '<spec>' (when it
    appears). This gives non-bullet reveal — a word appears on a step in sync
    with, e.g., its connector — without being a list item."""

    def test_mark_with_reveal(self):
        nodes = parse_inline("[theory]^a1<2-> rest", {})
        self.assertEqual(nodes[0]["type"], "mark")
        self.assertEqual(nodes[0]["name"], "a1")
        self.assertEqual(nodes[0]["reveal"], {"spec": "2-"})

    def test_reveal_span_without_name(self):
        nodes = parse_inline("an [aside]<3> here", {})
        span = [n for n in nodes if n["type"] == "span"][0]
        self.assertEqual(inline_text(span["content"]), "aside")
        self.assertEqual(span["reveal"], {"spec": "3"})

    def test_mark_without_spec_has_no_reveal(self):
        nodes = parse_inline("[m]^k", {})
        self.assertEqual(nodes[0]["type"], "mark")
        self.assertNotIn("reveal", nodes[0])

    def test_plain_brackets_stay_literal(self):
        # no '^name', '<spec>' or '@ref' suffix -> the brackets are just text
        nodes = parse_inline("see [1] for details", {})
        self.assertEqual(inline_types(nodes), ["text"])
        self.assertIn("[1]", nodes[0]["value"])

    def test_reveal_span_nests_markup(self):
        nodes = parse_inline("[a **bold** word]<1->", {})
        self.assertEqual(nodes[0]["type"], "span")
        self.assertIn("strong", inline_types(nodes[0]["content"]))


class TestRelativeSteps(unittest.TestCase):
    """Relative overlay specs '<+>' / '<+->' auto-allocate the next step (no
    manual numbering), in document order, across inline spans, '!when' blocks,
    and list items. A nested/following list item inherits the running step."""

    def test_inline_relative_specs_number_in_order(self):
        # resolved by the Parser during the scan (not parse_inline on its own)
        para = slide_nodes("!slide S\n[a]<+-> [b]<+-> [c]<+>\n")[0]
        specs = [c["reveal"]["spec"] for c in para["content"]
                 if c["type"] == "span"]
        self.assertEqual(specs, ["1-", "2-", "3"])   # cumulative, cumulative, only

    def test_relative_steps_flow_across_inline_and_when(self):
        deck = parse("!slide S\nintro\n\n[x]<+->\n\n!when<+->\n\tgated\n")
        body = deck_to_ast(deck)["body"]
        span = next(c for n in body for c in n.get("content", [])
                    if c["type"] == "span")
        gated = next(n for n in body if n["type"] == "para"
                     and inline_text(n["content"]) == "gated")
        self.assertEqual(span["reveal"]["spec"], "1-")
        self.assertEqual(gated["reveal"]["spec"], "2-")   # next step after the span

    def test_relative_spec_inside_code_is_not_resolved(self):
        # a literal ']<+>' inside a code span must be left alone
        para = slide_nodes("!slide S\n`arr]<+>` and [real]<+->\n")[0]
        code = [c for c in para["content"] if c["type"] == "code"][0]
        self.assertIn("]<+>", code["value"])              # untouched
        span = [c for c in para["content"] if c["type"] == "span"][0]
        self.assertEqual(span["reveal"]["spec"], "1-")

    def test_when_relative_spec(self):
        deck = parse("!slide S\n!when<+>\n\tflash\n\n!when<+->\n\tstay\n")
        nodes = deck_to_ast(deck)["body"]
        specs = [n["reveal"]["spec"] for n in nodes
                 if n["type"] == "para" and n.get("reveal")]
        self.assertEqual(specs, ["1", "2-"])              # bounded, then cumulative

    def test_nested_list_inherits_parent_step(self):
        # the user's example 1: nested '-' items appear with the parent '+'
        lst = slide_nodes("!slide S\n- a\n+ b\n\t- n1\n\t- n2\n")[0]
        sub = lst["items"][1]["sublist"]
        self.assertNotIn("reveal", lst["items"][0])       # 'a' static (step 0)
        self.assertEqual(lst["items"][1]["reveal"]["spec"], "1-")   # 'b'
        self.assertEqual([i["reveal"]["spec"] for i in sub["items"]],
                         ["1-", "1-"])                     # n1, n2 inherit b

    def test_nested_list_flows_with_inner_increment(self):
        # the user's example 2: a nested '+' advances, its '-' sibling joins it
        lst = slide_nodes("!slide S\n- a\n+ b\n\t+ n1\n\t- n2\n")[0]
        sub = lst["items"][1]["sublist"]
        self.assertEqual([i["reveal"]["spec"] for i in sub["items"]],
                         ["2-", "2-"])                     # both one after b


class TestSpacer(unittest.TestCase):
    """'!gap' is a vertical spacer: default, a fixed length, or 'fill'."""

    def test_gap_variants(self):
        deck = parse("!slide S\nA\n!gap\nB\n!gap[2em]\nC\n!gap[fill]\nD\n")
        sizes = [b.data.get("size") for b in deck.groups[0][0].blocks
                 if b.kind == "spacer"]
        self.assertEqual(sizes, [None, "2em", "fill"])

    def test_gap_ast(self):
        deck = parse("!slide S\nA\n!gap[1.5em]\n!gap[fill]\n")
        nodes = [block_to_ast(b, {}) for b in deck.groups[0][0].blocks
                 if b.kind == "spacer"]
        self.assertEqual(nodes[0], {"type": "spacer", "size": "1.5em"})
        self.assertEqual(nodes[1], {"type": "spacer", "size": "fill"})

    def test_default_gap_has_no_size(self):
        deck = parse("!slide S\nA\n!gap\n")
        node = block_to_ast(deck.groups[0][0].blocks[1], {})
        self.assertEqual(node, {"type": "spacer"})

    def test_bad_gap_size_fails(self):
        with self.assertRaises(LemurError):
            parse("!slide S\n!gap[sideways]\n")

    def test_gap_bare_size_is_rejected(self):
        # the size must be bracketed (the uniformity rule): '!gap 2em' is an error
        with self.assertRaises(LemurError) as cm:
            parse("!slide S\n!gap 2em\n")
        self.assertIn("bracket", str(cm.exception))


class TestConnect(unittest.TestCase):
    """'!connect' links two named marks with a directed, styled connector. Each
    line is its own step; the AST is neutral (from/to/dir/color/styles), no
    geometry — the emitter draws it (an arrow) or drops it (LaTeX)."""

    def test_parse_connect_style(self):
        # dotted style names, '#' colour (a bare word is now a colour, not a style)
        self.assertEqual(parse_connect_style("#c00"), ("#c00", []))
        self.assertEqual(parse_connect_style(".dashed"), (None, ["dashed"]))
        self.assertEqual(parse_connect_style("#c00 .thin"), ("#c00", ["thin"]))
        self.assertEqual(parse_connect_style(None), (None, []))

    def test_basic_link(self):
        deck = parse("!slide S\n[q]^q1 and [a]^a1\n\n!connect\n\tq1 -> a1 [#c00]\n")
        blk = deck.groups[0][0].blocks[1]
        self.assertEqual(blk.kind, "connect")
        lk = blk.data["links"][0]
        self.assertEqual((lk["from"], lk["to"], lk["dir"]), ("q1", "a1", "fwd"))
        self.assertEqual(lk["color"], "#c00")
        self.assertEqual(lk["step"], 1)

    def test_direction_glyphs(self):
        deck = parse("!slide S\n[a]^a [b]^b\n\n!connect\n"
                     "\ta -> b\n\ta <- b\n\ta <-> b\n\ta -- b\n")
        dirs = [lk["dir"] for lk in deck.groups[0][0].blocks[1].data["links"]]
        self.assertEqual(dirs, ["fwd", "back", "both", "none"])

    def test_each_line_is_a_step(self):
        deck = parse("!slide S\n[a]^a [b]^b [c]^c\n\n!connect\n"
                     "\ta -> b\n\tb -> c\n")
        steps = [lk["step"] for lk in deck.groups[0][0].blocks[1].data["links"]]
        self.assertEqual(steps, [1, 2])

    def test_connect_ast(self):
        deck = parse("!slide S\n[a]^a [b]^b\n\n!connect\n\ta <-> b [#2e5e6e .dashed]\n")
        node = block_to_ast(deck.groups[0][0].blocks[1], {})
        self.assertEqual(node["type"], "connect")
        lk = node["links"][0]
        self.assertEqual(lk["from"], "a")
        self.assertEqual(lk["to"], "b")
        self.assertEqual(lk["dir"], "both")
        self.assertEqual(lk["color"], "#2e5e6e")
        self.assertEqual(lk["styles"], ["dashed"])
        self.assertEqual(lk["reveal"], {"spec": "1-"})   # cumulative from step 1

    def test_plain_link_has_no_color_or_styles(self):
        deck = parse("!slide S\n[a]^a [b]^b\n\n!connect\n\ta -- b\n")
        node = block_to_ast(deck.groups[0][0].blocks[1], {})
        lk = node["links"][0]
        self.assertNotIn("color", lk)
        self.assertNotIn("styles", lk)
        self.assertEqual(lk["dir"], "none")

    def test_bad_connector_line_fails(self):
        with self.assertRaises(LemurError):
            parse("!slide S\n[a]^a\n\n!connect\n\tq1 => a1\n")

    def test_empty_connect_fails(self):
        with self.assertRaises(LemurError):
            parse("!slide S\n[a]^a\n\n!connect\n\t%% only a comment\n")


class TestEnvironments(unittest.TestCase):
    """Semantic environments ('!theorem', '!proof', …): one neutral 'env' node
    parameterised by kind, with an optional title/^ref and an indentation-
    delimited body of any blocks (including nested environments)."""

    def test_basic_environment(self):
        deck = parse("!slide S\n!theorem Pythagoras ^pyth\n"
                     "\tFor a right triangle, $a^2+b^2=c^2$.\n")
        blk = deck.groups[0][0].blocks[0]
        self.assertEqual(blk.kind, "env")
        self.assertEqual(blk.data["kind"], "theorem")
        self.assertEqual(blk.data["title"], "Pythagoras")
        node = block_to_ast(blk, {})
        self.assertEqual(node["type"], "env")
        self.assertEqual(node["kind"], "theorem")
        self.assertEqual(inline_text(node["title"]), "Pythagoras")
        self.assertEqual(node["id"], "pyth")
        self.assertEqual(node["body"][0]["type"], "para")

    def test_environment_without_title(self):
        deck = parse("!slide S\n!proof\n\tTrivial.\n")
        node = block_to_ast(deck.groups[0][0].blocks[0], {})
        self.assertEqual(node["kind"], "proof")
        self.assertNotIn("title", node)
        self.assertNotIn("id", node)

    def test_environment_holds_any_block(self):
        deck = parse("!slide S\n!example E\n\ttext\n\n\t:: math\n\t\tx=1\n\n"
                     "\t- a\n\t- b\n")
        node = block_to_ast(deck.groups[0][0].blocks[0], {})
        self.assertEqual([b["type"] for b in node["body"]],
                         ["para", "math", "list"])

    def test_nested_environment(self):
        deck = parse("!slide S\n!proof\n\touter\n\n\t!remark\n\t\tinner\n\n"
                     "\tafter inner\n")
        node = block_to_ast(deck.groups[0][0].blocks[0], {})
        kinds = [b.get("kind") if b["type"] == "env" else b["type"]
                 for b in node["body"]]
        self.assertEqual(kinds, ["para", "remark", "para"])

    def test_dedent_closes_environment(self):
        # content dedented back to slide level leaves the environment
        deck = parse("!slide S\n!theorem T\n\tinside\n\noutside\n")
        blocks = deck.groups[0][0].blocks
        self.assertEqual([b.kind for b in blocks], ["env", "para"])
        self.assertEqual(len(blocks[0].data["blocks"]), 1)   # only 'inside'

    def test_environment_inside_column(self):
        deck = parse("!slide S\n!columns[60,40]\n\t!column\n\t\t!theorem T\n"
                     "\t\t\tclaim\n\t!column\n\t\tplain\n")
        node = block_to_ast(deck.groups[0][0].blocks[0], {})
        # the theorem lives inside the first column, not at slide level
        self.assertEqual(node["columns"][0]["body"][0]["type"], "env")
        self.assertEqual(node["columns"][1]["body"][0]["type"], "para")

    def test_environment_reveal(self):
        deck = parse("!slide S\nbase\n!when<2->\n\t!theorem T\n\t\tclaim\n")
        node = block_to_ast(deck.groups[0][0].blocks[1], {})
        self.assertEqual(node["reveal"], {"spec": "2-"})

    def test_unknown_environment_is_unknown_directive(self):
        with self.assertRaises(LemurError):
            parse("!slide S\n!conjecture C\n\tmaybe\n")

    def test_columns_inside_environment_nests(self):
        # an env body may hold any block, including a '!columns' — all the
        # containers (env/columns/stack/layer) nest through one machinery
        deck = parse("!slide S\n!proof\n\t!columns\n\t\t!column\n\t\t\tx\n"
                     "\t\t!column\n\t\t\ty\n")
        env = block_to_ast(deck.groups[0][0].blocks[0], {})
        self.assertEqual(env["type"], "env")
        cols = env["body"][0]
        self.assertEqual(cols["type"], "columns")
        self.assertEqual(inline_text(cols["columns"][0]["body"][0]["content"]), "x")
        self.assertEqual(inline_text(cols["columns"][1]["body"][0]["content"]), "y")


class TestMathDelimiters(unittest.TestCase):
    def test_escaped_dollar_is_literal(self):
        nodes = parse_inline(r"it costs \$5 and \$6", {})
        self.assertEqual(inline_types(nodes), ["text"])   # no math
        self.assertIn("$5", nodes[0]["value"])
        self.assertIn("$6", nodes[0]["value"])

    def test_escaped_dollar_inside_math_stays_tex(self):
        # TeX needs the backslash inside math mode
        nodes = parse_inline(r"$\text{cost: \$5}$", {})
        self.assertEqual(nodes[0]["type"], "math")
        self.assertIn(r"\$5", nodes[0]["tex"])

    def test_dollar_in_code_span_untouched(self):
        nodes = parse_inline(r"use `awk '{print $1}'` here", {})
        code = [n for n in nodes if n["type"] == "code"][0]
        self.assertIn("print $1", code["value"])
        self.assertNotIn("math", inline_types(nodes))

    def test_math_then_escaped_dollar(self):
        nodes = parse_inline(r"$x^2$ costs \$3", {})
        self.assertEqual(nodes[0]["type"], "math")
        self.assertEqual(nodes[0]["tex"], "x^2")
        self.assertIn("$3", inline_text(nodes))

    def test_unbalanced_dollar_warns(self):
        buf = io.StringIO()
        with contextlib.redirect_stderr(buf):
            parse("!slide A\nthis costs $5 in total\n")
        self.assertIn("unbalanced '$'", buf.getvalue())

    def test_legacy_double_dollar_warns(self):
        buf = io.StringIO()
        with contextlib.redirect_stderr(buf):
            parse("!slide A\nsome $$x^2$$ math\n")
        self.assertIn("$$", buf.getvalue())

    def test_balanced_math_does_not_warn(self):
        buf = io.StringIO()
        with contextlib.redirect_stderr(buf):
            parse("!slide A\nsome $x^2$ math and a literal \\$ sign\n")
        self.assertEqual(buf.getvalue(), "")

    def test_warning_carries_location(self):
        buf = io.StringIO()
        with contextlib.redirect_stderr(buf):
            parse("!slide A\nfine text\n\nbad $ here\n")
        self.assertIn("test.lmr:4", buf.getvalue())


class TestComments(unittest.TestCase):
    def test_comment_lines_ignored(self):
        deck = parse("%% file header comment\n!slide A\n%% hidden\ntext\n")
        blocks = deck.groups[0][0].blocks
        self.assertEqual(len(blocks), 1)
        self.assertEqual(blocks[0].data["text"], "text")

    def test_comment_inside_paragraph_does_not_split_it(self):
        deck = parse("!slide A\nline one\n%% note to self\nline two\n")
        self.assertEqual(deck.groups[0][0].blocks[0].data["text"],
                         "line one line two")

    def test_escaped_percent_line(self):
        deck = parse("!slide A\n\\%% starts with literal percents\n")
        self.assertTrue(deck.groups[0][0].blocks[0].data["text"]
                        .startswith("%%"))

    def test_comment_in_table_rows(self):
        deck = parse("!slide A\n!table t\n!cols A, B\n"
                     "\t1 , 2\n\t%% 3 , 4\n\t5 , 6\n")
        rows = deck.groups[0][0].blocks[0].data["rows"]
        self.assertEqual(rows, [["1", "2"], ["5", "6"]])

    def test_comment_in_list(self):
        deck = parse("!slide A\n- one\n%% - two\n- three\n")
        texts = [i[1] for i in deck.groups[0][0].blocks[0].data["items"]]
        self.assertEqual(texts, ["one", "three"])

    def test_comment_in_annotate_body(self):
        deck = parse("!slide A\n:: math\n\t\\mk{s}{x}\n\n!annotate\n"
                     "\t%% disabled: old label\n\ts: the part\n")
        items = deck.groups[0][0].blocks[1].data["items"]
        self.assertEqual(len(items), 1)

    def test_code_block_body_keeps_percent_lines(self):
        # '%%' is meaningful in e.g. Erlang and MATLAB; verbatim blocks
        # must not treat it as a lemur comment
        deck = parse("!slide A\n:: erlang\n\t%% erlang comment\n\tok.\n")
        self.assertIn("%% erlang comment",
                      deck.groups[0][0].blocks[0].data["text"])


class TestIndentation(unittest.TestCase):
    def test_first_line_defines_prefix(self):
        deck = parse("!slide A\n:: c\n        int x;\n        int y;\n")
        self.assertEqual(deck.groups[0][0].blocks[0].data["text"],
                         "int x;\nint y;")

    def test_deeper_indent_is_content(self):
        deck = parse("!slide A\n:: python\n\tdef f():\n\t\treturn 1\n")
        self.assertEqual(deck.groups[0][0].blocks[0].data["text"],
                         "def f():\n\treturn 1")

    def test_mixed_indent_within_block_fails(self):
        with self.assertRaises(LemurError) as cm:
            parse("!slide A\n:: c\n\tint x;\n    int y;\n")
        self.assertIn("inconsistent indentation", str(cm.exception))

    def test_different_blocks_different_indents(self):
        deck = parse("!slide A\n:: c\n\tint x;\n\n:: c\n   int y;\n")
        blocks = deck.groups[0][0].blocks
        self.assertEqual(blocks[0].data["text"], "int x;")
        self.assertEqual(blocks[1].data["text"], "int y;")

    def test_dedent_ends_block_normally(self):
        deck = parse("!slide A\n:: c\n\tint x;\nafter the block\n")
        self.assertEqual(deck.groups[0][0].blocks[1].data["text"],
                         "after the block")


class TestStepModel(unittest.TestCase):
    """The activation (step) model: '!pause', '+' items and extra image layers
    each get an increasing data-appear step (Plan.md Section 4.3)."""

    def test_pause_wraps_following_blocks(self):
        # 'base' is step 0 (no step); the two later paragraphs get steps 1, 2
        src = "!slide A\nbase\n\n!pause\n\nafter one\n\n!pause\n\nafter two"
        self.assertEqual(appear_steps(slide_nodes(src)), [1, 2])

    def test_plus_items_each_step(self):
        # '-' item has no step; the two '+' items step 1 and 2
        self.assertEqual(appear_steps(slide_nodes("!slide A\n- static\n+ one\n+ two\n")),
                         [1, 2])

    def test_minus_items_are_base(self):
        self.assertEqual(appear_steps(slide_nodes("!slide A\n- a\n- b\n")), [])

    def test_image_layers_step(self):
        deck = parse("!slide A\n!img\n!src a.svg\n!src b.svg\n!src c.svg\n")
        blk = deck.groups[0][0].blocks[0]
        self.assertEqual(blk.data["layer_steps"], [1, 2])  # 2 extra layers
        self.assertEqual(
            appear_steps(paginate(deck_to_ast(deck)["body"])[0]["nodes"]), [1, 2])

    def test_pause_then_image_layers_compose(self):
        # a figure after a pause: the block is gated at the pause step, its
        # extra layers step above it
        src = "!slide A\nintro\n\n!pause\n\n!img\n!src a.svg\n!src b.svg\n"
        self.assertEqual(appear_steps(slide_nodes(src)), [1, 2])  # wrapper=1, layer=2

    def test_steps_reset_per_slide(self):
        slides = deck_slides("!slide A\nx\n!pause\ny\n!slide B\nz\n!pause\nw\n")
        self.assertEqual(appear_steps(slides[0]["nodes"]), [1])
        self.assertEqual(appear_steps(slides[1]["nodes"]), [1])  # B restarts at 1

    def test_notes_never_get_appear(self):
        # the note is hidden by css, never gated by a step it would never reach
        src = "!slide A\nx\n!pause\n!notes\n\thidden note\n"
        self.assertEqual(appear_steps(slide_nodes(src)), [])


class TestOverlays(unittest.TestCase):
    """Explicit overlay specs ('when to show') on list items and blocks (Q2):
    '+<2->', '-<3>', '!when<2-4>' -> data-when."""

    def test_list_item_overlay_specs(self):
        nodes = slide_nodes("!slide A\n- static\n+<2-> from two\n-<3> only three\n")
        # each item's explicit overlay spec becomes its reveal (in order); the
        # static item carries none
        self.assertEqual(reveal_specs(nodes), ["2-", "3"])

    def test_when_block_gates_its_indented_body(self):
        # '!when' is indentation-delimited: its whole body is gated; a dedent
        # ends it and content after is ungated
        deck = parse("!slide A\nbase\n!when<2-3>\n\tfirst\n\n\tsecond\n\nafter\n")
        blocks = deck.groups[0][0].blocks
        self.assertEqual([b.when for b in blocks], [None, "2-3", "2-3", None])
        nodes = paginate(deck_to_ast(deck)["body"])[0]["nodes"]
        self.assertNotIn("reveal", nodes[0])                 # base content
        self.assertEqual(nodes[1]["reveal"]["spec"], "2-3")  # in the body
        self.assertEqual(nodes[2]["reveal"]["spec"], "2-3")  # still in the body
        self.assertNotIn("reveal", nodes[3])                 # dedented out

    def test_when_blocks_nest_and_narrow(self):
        # a nested '!when' narrows; the outer scope resumes after it dedents
        deck = parse("!slide A\n!when<1->\n\tA\n\n\t!when<3->\n\t\tB\n\n\tC\n")
        specs = [b.when for b in deck.groups[0][0].blocks]
        self.assertEqual(specs, ["1-", "3-", "1-"])          # A, B, C

    def test_when_without_indented_body_fails(self):
        # a flat '!when' (no indented body) would silently gate nothing
        with self.assertRaises(LemurError) as cm:
            parse("!slide A\n!when<2->\nnot indented\n")
        self.assertIn("indented body", str(cm.exception))

    def test_when_bare_spec_is_rejected(self):
        # the spec must be in angle brackets ('!when<2->'), not bare ('!when 2-')
        with self.assertRaises(LemurError) as cm:
            parse("!slide A\n!when 2-\n\tgated\n")
        self.assertIn("angle brackets", str(cm.exception))

    def test_when_gates_any_block_kind(self):
        # the reported bug: a code block in the body is gated too, not just prose
        deck = parse("!slide A\n!when<1->\n\ttext\n\n\t:: python\n\t\tx = 1\n")
        kinds = [(b.kind, b.when) for b in deck.groups[0][0].blocks]
        self.assertEqual(kinds, [("para", "1-"), ("code", "1-")])

    def test_invalid_overlay_spec_fails(self):
        for bad in ("!slide A\n!when abc\n\tx\n", "!slide A\n+<xyz> item\n"):
            with self.assertRaises(LemurError):
                parse(bad)


class TestStacks(unittest.TestCase):
    """Stacked overlays: '!stack' + '!layer<spec>' overlap in one grid cell so
    a layer takes the place of the previous one (item 4)."""

    def test_stack_parse_and_render(self):
        deck = parse("!slide A\n!stack\n\t!layer<1>\n\t\tfirst\n"
                     "\t!layer<2->\n\t\tsecond\n")
        blk = deck.groups[0][0].blocks[0]
        self.assertEqual(blk.kind, "stack")
        self.assertEqual(len(blk.data["layers"]), 2)
        self.assertEqual(blk.data["layers"][0]["when"], "1")
        self.assertEqual(blk.data["layers"][1]["when"], "2-")
        self.assertEqual(
            blk.data["layers"][0]["blocks"][0].data["text"], "first")
        # the stack recurses into structured layers in the AST
        node = block_to_ast(blk, {})
        self.assertEqual(node["type"], "stack")
        self.assertEqual([lyr["reveal"]["spec"] for lyr in node["layers"]], ["1", "2-"])
        self.assertEqual(inline_text(node["layers"][0]["body"][0]["content"]), "first")

    def test_layer_spec_must_be_bracketed(self):
        # the spec uses the attached '<…>' bracket; the old bare '!layer 2-' form
        # is gone (uniform with '!when<…>' and '+<…>')
        deck = parse("!slide A\n!stack\n\t!layer<2->\n\t\tx\n")
        self.assertEqual(
            deck.groups[0][0].blocks[0].data["layers"][0]["when"], "2-")
        with self.assertRaises(LemurError):
            parse("!slide A\n!stack\n\t!layer 2-\n\t\tx\n")

    def test_layer_without_spec_fails(self):
        with self.assertRaises(LemurError):
            parse("!slide A\n!stack\n\t!layer\n\t\tx\n")

    def test_layer_outside_stack_fails(self):
        with self.assertRaises(LemurError):
            parse("!slide A\n!layer<1>\nx\n")

    def test_invalid_layer_spec_fails(self):
        with self.assertRaises(LemurError):
            parse("!slide A\n!stack\n\t!layer<abc>\n\t\tx\n")

    def test_dedent_ends_stack(self):
        deck = parse("!slide A\n!stack\n\t!layer<1>\n\t\tin layer\n"
                     "back at slide level\n")
        blocks = deck.groups[0][0].blocks
        self.assertEqual(blocks[0].kind, "stack")
        self.assertEqual(blocks[1].kind, "para")
        self.assertIn("back at slide level", blocks[1].data["text"])

    def test_stacks_do_not_cross_slides(self):
        deck = parse("!slide A\n!stack\n\t!layer<1>\n\t\tx\n!slide B\ny\n")
        self.assertEqual(deck.groups[1][0].blocks[0].data["text"], "y")


class TestLogo(unittest.TestCase):
    """'!logo path' meta puts a corporate logo on content slides (item 6)."""

    def test_logo_in_chrome(self):
        # the logo is deck-level chrome; the runtime places it on content slides
        # (and drops it on sections) — see the render.test.mjs unit tests
        a = deck_to_ast(parse(
            "!title T\n!logo figs/logo.svg\n!slide One\nx\n# Section ^s\n"))
        self.assertEqual(a["presentation"]["logo"], "figs/logo.svg")

    def test_logo_is_copied_as_a_figure(self):
        from lemur.emit.slides import _iter_img_srcs   # figure collection is the emitter's
        deck = parse("!title T\n!logo brand.png\n!slide One\nx\n")
        self.assertIn("brand.png", list(_iter_img_srcs(deck)))


class TestBracketSyntax(unittest.TestCase):
    """The unified no-space option bracket (item 2)."""

    def test_spaced_annotation_bracket_is_rejected(self):
        # the option bracket must attach with no space; the old spaced form
        # 'name [color]: text' no longer parses (hard switch)
        with self.assertRaises(LemurError):
            parse("!slide A\ntext [w]^k\n\n!annotate\n\tk [#c00]: label\n")

    def test_code_line_spec_attaches_with_no_space(self):
        deck = parse("!slide A\n:: python[1|2]\n\ta\n\tb\n")
        self.assertEqual(deck.groups[0][0].blocks[0].data["lines"], "1|2")

    def test_heading_option_bracket(self):
        deck = parse("#[.center .plain] Big\ntext\n")
        self.assertEqual(deck.groups[0][0].styles, ["center", "plain"])


class TestAST(unittest.TestCase):
    """The AST is the single source of truth for the shipped build: parse -> AST
    -> JSON, rendered to DOM at runtime. Every block and inline run is a fully-
    typed node; lemur.parser emits no html."""

    def test_deck_structure(self):
        a = deck_to_ast(parse(
            "!title T\n!subtitle S\n!author A\n# Sec ^s\n!slide One\nx\n"))
        self.assertEqual(a["astVersion"], 1)
        self.assertEqual(a["meta"]["title"], "T")
        self.assertEqual(a["meta"]["subtitle"], "S")
        self.assertEqual(a["meta"]["authors"], ["A"])
        # no cover synthesis, design box, or chrome in the neutral document AST
        self.assertNotIn("design", a)
        self.assertNotIn("slides", a)
        # slides are a pagination view: a pagebreak per !slide / '# Section'
        pages = paginate(a["body"])
        self.assertEqual(len(pages), 2)              # Sec + One
        self.assertEqual(pages[0]["role"], "section")
        self.assertEqual(pages[0]["id"], "s")        # the '^s' label
        self.assertEqual(inline_text(pages[1]["title"]), "One")

    def test_para_and_math_are_structured(self):
        nodes = slide_nodes("!slide A\nhello **world**\n\n:: math\n\tx^2\n")
        self.assertEqual(nodes[0]["type"], "para")
        self.assertEqual(inline_types(nodes[0]["content"]), ["text", "strong"])
        self.assertEqual(inline_text(nodes[0]["content"][1]["content"]), "world")
        self.assertEqual(nodes[1]["type"], "math")
        self.assertEqual(nodes[1]["tex"], "x^2")

    def test_columns_recurse(self):
        cols = slide_nodes(
            "!slide A\n!columns[60,40]\n\t!column\n\t\tleft\n\t!column\n\t\tright\n")[0]
        self.assertEqual(cols["type"], "columns")
        self.assertEqual([c["weight"] for c in cols["columns"]], [60.0, 40.0])
        self.assertEqual(len(cols["columns"]), 2)
        self.assertEqual(inline_text(cols["columns"][0]["body"][0]["content"]), "left")

    def test_stack_layers(self):
        stack = slide_nodes(
            "!slide A\n!stack\n\t!layer<1>\n\t\tone\n\t!layer<2->\n\t\ttwo\n")[0]
        self.assertEqual(stack["type"], "stack")
        self.assertEqual([l["reveal"]["spec"] for l in stack["layers"]], ["1", "2-"])
        self.assertEqual(inline_text(stack["layers"][0]["body"][0]["content"]), "one")

    def test_list_is_structured(self):
        lst = slide_nodes("!slide A\n- item\n+ frag\n")[0]
        self.assertEqual(lst["type"], "list")
        self.assertEqual(inline_text(lst["items"][0]["content"]), "item")
        self.assertEqual(lst["items"][1]["reveal"]["spec"], "1-")   # the '+' item
        self.assertEqual(inline_text(lst["items"][1]["content"]), "frag")

    def test_nested_list(self):
        items = slide_nodes("!slide A\n- top\n\t- child\n- back\n")[0]["items"]
        self.assertEqual([inline_text(i["content"]) for i in items], ["top", "back"])
        self.assertEqual(
            inline_text(items[0]["sublist"]["items"][0]["content"]), "child")

    def test_star_is_a_static_bullet_alias(self):
        # '*' behaves like '-': an unordered, static (non-incremental) bullet,
        # and nests by indentation like the others
        lst = slide_nodes("!slide A\n* one\n  * nested\n* two\n")[0]
        self.assertEqual(lst["type"], "list")
        self.assertFalse(lst["ordered"])
        self.assertNotIn("reveal", lst["items"][0])          # static, no step
        self.assertEqual(
            inline_text(lst["items"][0]["sublist"]["items"][0]["content"]),
            "nested")

    def test_reveal_specs(self):
        nodes = slide_nodes(
            "!slide A\nbase\n\n!pause\n\nlater\n\n!when<2-3>\n\tgated\n")
        self.assertNotIn("reveal", nodes[0])                  # base content
        self.assertEqual(nodes[1]["reveal"]["spec"], "1-")    # after !pause
        self.assertEqual(nodes[2]["reveal"]["spec"], "2-3")   # !when gate

    def test_labelled_block_carries_id(self):
        # a '^ref' becomes the block's symbolic cross-reference id; unlabelled
        # blocks carry no id (the neutral AST has no DOM ids)
        nodes = slide_nodes("!slide A\n### Head ^h\n\nplain\n")
        self.assertEqual(nodes[0]["type"], "heading")
        self.assertEqual(nodes[0]["id"], "h")
        self.assertNotIn("id", nodes[1])

    def test_chrome_and_logo(self):
        p = deck_to_ast(parse(
            "!title T\n!header H\n!logo l.svg\n!slide A\nx\n"))["presentation"]
        self.assertEqual(inline_text(p["header"]), "H")
        self.assertEqual(p["logo"], "l.svg")

    def test_progress_hint(self):
        # '!progress [top|bottom]' is a presentation hint; 'off'/absent omits it
        def prog(src):
            return deck_to_ast(parse(src)).get("presentation", {}).get("progress")
        self.assertEqual(prog("!progress bottom\n!slide A\nx\n"),
                         {"position": "bottom"})
        self.assertEqual(prog("!progress\n!slide A\nx\n"), True)   # bare -> on
        self.assertIsNone(prog("!progress off\n!slide A\nx\n"))
        self.assertIsNone(prog("!slide A\nx\n"))

    def test_parse_transition_new_values(self):
        self.assertEqual(parse_transition({"transition": "slide rise"}),
                         ("slide", "rise"))
        self.assertEqual(parse_transition({}), ("none", "fade"))
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(parse_transition({"transition": "wobble"}),
                             ("none", "fade"))

    def test_build_renders_deck_dom_at_build_time(self):
        # the shipped index.html carries the real slide DOM (lemur.emit.html), not
        # an embedded AST — the product does not depend on the AST at runtime
        with tempfile.TemporaryDirectory() as d:
            master = os.path.join(d, "m.lmr")
            with open(master, "w") as fh:
                fh.write("!title T\n!slide One\nsome $x^2$ content\n")
            out = os.path.join(d, "build")
            build(master, out)
            html_doc = open(os.path.join(out, "index.html")).read()
            self.assertNotIn('id="lmr-deck"', html_doc)       # no embedded AST
            self.assertIn('class="slide cover"', html_doc)     # cover, rendered
            self.assertIn('class="slide content"', html_doc)   # the '!slide One'
            self.assertIn("some ", html_doc)                   # its text content
            self.assertIn("\\(x^2\\)", html_doc)               # inline math, inlined
            self.assertNotIn("reveal", html_doc.lower())


class TestTemplateEngine(unittest.TestCase):
    """The {{key}} / {{?key}}...{{/key}} substitution engine (unchanged)."""

    def test_substitution(self):
        out = render_template("a {{x}} b", {"x": "1"})
        self.assertEqual(out, "a 1 b")

    def test_conditional_kept_and_dropped(self):
        t = "{{?img}}<img src='{{img}}'>{{/img}}end"
        self.assertEqual(render_template(t, {"img": "p.svg"}),
                         "<img src='p.svg'>end")
        # placeholders inside a dropped conditional vanish with it
        self.assertEqual(render_template(t, {"img": ""}), "end")

    def test_nested_conditionals_different_keys(self):
        t = "{{?a}}A{{?b}}B{{/b}}{{/a}}"
        self.assertEqual(render_template(t, {"a": "x", "b": "y"}), "AB")
        self.assertEqual(render_template(t, {"a": "x", "b": ""}), "A")
        self.assertEqual(render_template(t, {"a": "", "b": "y"}), "")

    def test_unknown_placeholder_left_verbatim_with_warning(self):
        buf = io.StringIO()
        with contextlib.redirect_stderr(buf):
            out = render_template("keep {{mystery}}", {})
        self.assertEqual(out, "keep {{mystery}}")
        self.assertIn("mystery", buf.getvalue())

    def test_user_content_is_not_rescanned(self):
        # slide content containing template syntax must not be interpreted
        out = render_template("{{slides}}", {"slides": "{{title}} {{?x}}"})
        self.assertEqual(out, "{{title}} {{?x}}")


class TestThemes(unittest.TestCase):
    """Theme resolution: a theme is a 'themes/<name>/' dir with a theme.css;
    slides.css = base.css + theme.css."""

    def test_shipped_theme_set(self):
        names = {n for n, _, _ in list_themes()}
        self.assertTrue({"clean", "journal", "dark"} <= names)

    def test_shipped_themes_load(self):
        for name, _dir, _desc in list_themes():
            css = load_theme(name)
            # slides.css = base structure + theme tokens
            self.assertIn(".deck", css, name)
            self.assertIn("--lmr-accent", css, name)

    def test_theme_desc_from_first_comment(self):
        for name, _dir, desc in list_themes():
            self.assertTrue(desc, name)  # every shipped theme has a description
            # a multi-line comment must not leak into the one-line description
            self.assertNotIn("\n", desc, name)
            self.assertNotIn(" * ", desc, name)

    def test_theme_tokens_customize_chrome_and_background(self):
        # base.css consumes the customization tokens (item 3)
        base_css = load_theme("clean")
        self.assertIn("var(--lmr-bg-image", base_css)
        self.assertIn("var(--lmr-chrome-size", base_css)
        self.assertIn("var(--lmr-chrome-ink", base_css)
        # the gradient sample theme sets a background + custom chrome
        grad = load_theme("gradient")
        self.assertIn("--lmr-bg-image:", grad)
        self.assertIn("--lmr-chrome-transform:", grad)

    def test_unknown_theme_lists_search_path(self):
        with self.assertRaises(LemurError) as cm:
            find_theme("nonexistent")
        self.assertIn("nonexistent/theme.css", str(cm.exception))
        self.assertIn("themes", str(cm.exception))

    def test_document_local_shadows_shipped(self):
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "themes", "clean"))
            with open(os.path.join(d, "themes", "clean", "theme.css"),
                      "w") as fh:
                fh.write("/* shadowed */ :root{--lmr-accent:#abcdef}")
            master = os.path.join(d, "m.lmr")
            with open(master, "w") as fh:
                fh.write("!slide A\nx\n")
            doc_dir = os.path.dirname(os.path.abspath(master))
            css = load_theme("clean", doc_dir)
            self.assertIn("#abcdef", css)
            # shipped theme still found for documents elsewhere
            css2 = load_theme("clean")
            self.assertNotIn("#abcdef", css2)

    def test_theme_dir_flag_beats_document_local(self):
        with tempfile.TemporaryDirectory() as d:
            extra = os.path.join(d, "extra")
            os.makedirs(os.path.join(extra, "clean"))
            with open(os.path.join(extra, "clean", "theme.css"), "w") as fh:
                fh.write("/* extra */ :root{--lmr-accent:#111111}")
            os.makedirs(os.path.join(d, "themes", "clean"))
            with open(os.path.join(d, "themes", "clean", "theme.css"),
                      "w") as fh:
                fh.write("/* local */ :root{--lmr-accent:#222222}")
            css = load_theme("clean", d, extra)
            self.assertIn("#111111", css)

    def test_env_var_on_search_path(self):
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "mine"))
            with open(os.path.join(d, "mine", "theme.css"), "w") as fh:
                fh.write("/* env */ :root{--lmr-accent:#333333}")
            old = os.environ.get("LEMUR_THEMES")
            os.environ["LEMUR_THEMES"] = d
            try:
                theme_dir = find_theme("mine")
                self.assertEqual(os.path.dirname(theme_dir), d)
            finally:
                if old is None:
                    del os.environ["LEMUR_THEMES"]
                else:
                    os.environ["LEMUR_THEMES"] = old

    def test_theme_as_path(self):
        with tempfile.TemporaryDirectory() as d:
            own = os.path.join(d, "own")
            os.makedirs(own)
            with open(os.path.join(own, "theme.css"), "w") as fh:
                fh.write("/* own */ :root{--lmr-accent:#444444}")
            css = load_theme(own)
            self.assertIn("#444444", css)

    def test_missing_theme_path_errors(self):
        with self.assertRaises(LemurError):
            find_theme("/does/not/exist")

    def test_resolve_theme_precedence(self):
        self.assertEqual(resolve_theme_name({"theme": "dark"}, None), "dark")
        self.assertEqual(resolve_theme_name({"theme": "dark"}, "journal"),
                         "journal")
        self.assertEqual(resolve_theme_name({}, None), "clean")


class TestBuild(unittest.TestCase):
    """The output folder: index.html + slides.css + runtime.js + figures."""

    def _master(self, d, body):
        master = os.path.join(d, "m.lmr")
        with open(master, "w") as fh:
            fh.write(body)
        return master

    def test_theme_selection_via_directive(self):
        # '!theme dark' selects the dark theme; its accent lands in slides.css
        css = load_theme("dark")
        self.assertIn("--lmr-accent: #7fb8cc", css)

    def test_cli_theme_overrides_directive(self):
        with tempfile.TemporaryDirectory() as d:
            master = self._master(d, "!title T\n!theme dark\n!slide A\nx\n")
            out = os.path.join(d, "site")
            build(master, out, theme="journal")
            with open(os.path.join(out, "slides.css")) as fh:
                css = fh.read()
            self.assertIn("--lmr-accent: #8a2f2f", css)  # journal, not dark

    def test_build_writes_folder(self):
        with tempfile.TemporaryDirectory() as d:
            master = self._master(
                d, "!title T\n!slide A\nhello world\n")
            out = os.path.join(d, "site")
            build(master, out)
            for f in ("index.html", "slides.css", "runtime.js"):
                self.assertTrue(os.path.exists(os.path.join(out, f)), f)
            with open(os.path.join(out, "index.html")) as fh:
                html_doc = fh.read()
            self.assertIn("hello world", html_doc)
            self.assertIn('class="deck"', html_doc)
            self.assertNotIn("Reveal", html_doc)

    def test_build_copies_figures(self):
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "figs"))
            with open(os.path.join(d, "figs", "a.svg"), "w") as fh:
                fh.write("<svg/>")
            master = self._master(
                d, "!slide A\n!img\n!src figs/a.svg\n")
            out = os.path.join(d, "site")
            build(master, out)
            self.assertTrue(
                os.path.exists(os.path.join(out, "figs", "a.svg")))

    def test_build_bundles_fonts(self):
        # the deck ships its own OFL fonts (+ @font-face) so layout is identical
        # on every machine/browser — no reliance on installed system fonts
        with tempfile.TemporaryDirectory() as d:
            master = self._master(d, "!slide A\nhello `code`\n")
            out = os.path.join(d, "site")
            build(master, out)
            fonts = os.listdir(os.path.join(out, "fonts"))
            for fam in ("source-sans-3", "source-serif-4", "jetbrains-mono"):
                self.assertIn(f"{fam}-normal.woff2", fonts)   # variable families
                self.assertIn(f"{fam}-italic.woff2", fonts)
                self.assertIn(f"OFL-{fam}.txt", fonts)   # OFL requires it ships
            # Libre Baskerville is static: three explicit weights, its own license
            for fn in ("libre-baskerville-400-normal.woff2",
                       "libre-baskerville-400-italic.woff2",
                       "libre-baskerville-700-normal.woff2",
                       "OFL-libre-baskerville.txt"):
                self.assertIn(fn, fonts)
            with open(os.path.join(out, "slides.css")) as fh:
                css = fh.read()
            self.assertIn("@font-face", css)
            self.assertIn('url("fonts/source-sans-3-normal.woff2")', css)
            self.assertIn('url("fonts/libre-baskerville-700-normal.woff2")', css)
            # the bundled family is named ahead of any system fallback
            self.assertIn('"Source Sans 3"', css)

    def test_journal_theme_uses_bundled_serifs(self):
        css = load_theme("journal")
        # journal's serif stack leads with the two bundled serifs (order is the
        # author's taste — they toggle between them), ahead of any system serif.
        # base.css now declares a default for every token, so the theme's override
        # is the LAST matching line (it is concatenated after base and wins).
        for var in ("--lmr-font", "--lmr-heading-font"):
            line = [ln for ln in css.splitlines() if var + ":" in ln][-1]
            self.assertIn('"Source Serif 4"', line)
            self.assertIn('"Libre Baskerville"', line)

    def test_title_image_is_a_presentation_hint(self):
        # no cover in the neutral AST; the title image is a presentation hint the
        # emitter may use when it synthesizes one
        with_img = deck_to_ast(parse(
            "!title T\n!titleimage figs/hero.svg\n!slide A\nx\n"))
        self.assertEqual(with_img["presentation"]["titleImage"], "figs/hero.svg")
        without = deck_to_ast(parse("!title T\n!slide A\nx\n"))
        self.assertNotIn("titleImage", without.get("presentation", {}))

    def test_subtitle_is_metadata(self):
        a = deck_to_ast(parse(
            "!title T\n!subtitle A grand tour\n!slide A\nx\n"))
        self.assertEqual(a["meta"]["subtitle"], "A grand tour")

    def test_no_title_no_cover(self):
        # the AST has no cover concept; without a title there is simply no title
        a = deck_to_ast(parse("!slide A\nx\n"))
        self.assertNotIn("title", a["meta"])
        self.assertEqual(paginate(a["body"])[0].get("role", "content"), "content")


class TestAudit(unittest.TestCase):
    """Size and dependency audit guards (Plan.md Section 9/12.9): the shipped
    deck stays reveal-free and small."""

    def _example(self):
        here = os.path.dirname(__file__)
        return os.path.join(here, "..", "..", "examples", "lecture", "master.lmr")

    def test_shipped_output_is_reveal_free(self):
        import re as _re
        with tempfile.TemporaryDirectory() as d:
            build(self._example(), d)
            blob = ""
            for fn in ("index.html", "slides.css", "runtime.js"):
                with open(os.path.join(d, fn)) as fh:
                    blob += fh.read()
            # target reveal.js's own signatures, not the bare word 'reveal'
            # (which is now a lemur AST concept — a reveal spec)
            self.assertFalse(
                _re.search(r"reveal\.js|Reveal\.(initialize|configure)|"
                           r"new\s+Reveal|class=\"reveal\"|\br-stack\b|"
                           r"\br-fit-text\b|data-transition-speed", blob),
                "no reveal.js artifacts in shipped output")
            # MathJax is the only runtime dependency, from the CDN by default
            self.assertIn("mathjax", blob)
            self.assertNotIn("katex", blob.lower())

    def test_renderer_assets_stay_small(self):
        # a regression tripwire, not a hard budget: our first-party shipped
        # assets are tiny (reveal was ~1 MB). index.html is the pretty-printed
        # AST (readable for debugging), so it is the largest. Generous ceilings.
        with tempfile.TemporaryDirectory() as d:
            build(self._example(), d)
            sizes = {fn: os.path.getsize(os.path.join(d, fn))
                     for fn in ("runtime.js", "slides.css", "index.html")}
            # behavior-only since the render engine moved to lemur.emit.html
            # (Plan-DisplayModel Phase 3); the tripwire dropped ~24 KB with it
            self.assertLess(sizes["runtime.js"], 56_000, sizes)
            # slides.css carries the centralized :root design-token block
            # (Plan-DisplayModel §3.3 / Phase 1) — an intentional ~2.6 KB
            self.assertLess(sizes["slides.css"], 48_000, sizes)
            self.assertLess(sizes["index.html"], 80_000, sizes)
            self.assertLess(sum(sizes.values()), 180_000, sizes)


class TestErrors(unittest.TestCase):
    def test_unknown_directive_reports_location(self):
        with self.assertRaises(LemurError) as cm:
            parse("!slide A\n!bogus arg\n")
        self.assertIn("test.lmr:2", str(cm.exception))

    def test_pause_outside_slide(self):
        with self.assertRaises(LemurError):
            parse("!pause")

    def test_table_without_cols(self):
        with self.assertRaises(LemurError):
            parse("!slide A\n!table t\n\ttext row\n")


if __name__ == "__main__":
    unittest.main()
