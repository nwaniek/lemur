#!/usr/bin/env python3
r"""lemur.parser - parse Lemur (.lmr) documents into the neutral document AST.

Lemur is a light markup language inspired by reStructuredText, Markdown, and
LaTeX. This module is the **parser** only: it turns a `.lmr` document into the
neutral AST (spec/ast.schema.json, the `lemur.ast` contract) and knows nothing
about any output format. The emitters consume the AST — `lemur.emit.slides`
(a self-contained HTML deck) and a LaTeX emitter (planned). Run
`python3 lmr2ast.py doc.lmr` to print the AST as JSON, or pipe it:
`python3 lmr2ast.py doc.lmr | python3 lmr2slides.py -o out/`.
See Plan-DisplayModel.md.

It implements the language as described in spec/spec.lmr plus a small set of
slide-oriented extensions:

    !include path.lmr         include another file (master-file workflow)
    !slide[.style] Title ^ref start a slide; '[.style]' adds a css class
    #[.style] Title ^ref      section divider slide (big title)
    !pause                    step boundary: content after it appears on the
                              next keypress (compiles to data-appear)
    !stack / !layer<spec>     overlapping layers: each '!layer' shows per its
                              overlay spec, taking the place of the previous
    !notes                    indented block below becomes speaker notes
                              (parsed, hidden in the interactive deck)
    !annotate                 indented 'name[color]: text' lines attach
                              highlights and arrows to named marks (see '\mk')
    :: math                   display math block (LaTeX, MathJax at runtime)
    + item                    incremental list item; '-' is static
    %% ...                    comment line, ignored (lemur 0.0.2)

Options (style classes, annotation colors, code line ranges) go in a bracket
attached with no space right after the directive/name: '!slide[.center] ...',
'#[.hero] ...', ':: python[1|4-6] ...', 'fac[#7a4b94]: ...'. References keep
their trailing '^ref' form.

The AST is the single source of truth and the only interface to the emitters
(no output-specific knowledge leaks into the parser), so a new output format is a
new consumer of the same AST, never a change here. Parsing — and all its
diagnostics — stays in Python; how a deck looks is entirely the emitter's
concern. See lemur.emit.slides for the reference HTML emitter.
There is no reveal.js.

Inline math uses a single '$' since lemur 0.0.2; literal dollars in text are
escaped as '\$'. Block bodies follow the first-line-defines-indent rule: the
leading whitespace of a block's first line must prefix every further line.

Slide images ('!img') accept multiple '!src' lines; each additional layer is
revealed step by step. '!mode replace' switches from overlay to replacement.

Document configuration (before the first slide):
    !title / !subtitle / !author / !institute / !date / !titleimage / !logo
    !header / !footer / !slidenumbers <on|off>
    !theme <name> / !transition <none|fade> / !aspect <16:9|4:3>

Usage:
    python3 lmr2ast.py examples/lecture/master.lmr --ast   # print the neutral AST
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from dataclasses import dataclass, field
from typing import Optional

from . import ast as lmrast  # the shared AST contract (version, vocabulary, load/dump)

# --------------------------------------------------------------------------
# errors and source tracking
# --------------------------------------------------------------------------


class LemurError(Exception):
    """Compilation error carrying file/line information for diagnostics.
    Errors without a source location (e.g. template resolution) omit the
    'file:line:' prefix instead of printing a placeholder."""

    def __init__(self, message: str, filename: str = "", lineno: int = 0):
        prefix = f"{filename}:{lineno}: " if filename else ""
        super().__init__(prefix + message)
        self.filename = filename
        self.lineno = lineno


@dataclass
class Line:
    """A physical source line annotated with its origin (for error messages
    and because '!include' flattens multiple files into one stream)."""

    file: str
    no: int
    text: str

    @property
    def indent(self) -> int:
        # tabs are expanded so that tab- and space-indented files behave the
        # same; README.lmr uses tabs, but contributors may use spaces
        expanded = self.text.expandtabs(4)
        return len(expanded) - len(expanded.lstrip(" "))

    @property
    def stripped(self) -> str:
        return self.text.strip()

    @property
    def blank(self) -> bool:
        return self.stripped == ""


def leading_ws(text: str) -> str:
    """Return the exact leading whitespace (tabs and spaces) of a line."""
    return text[:len(text) - len(text.lstrip(" \t"))]


def is_comment(text: str) -> bool:
    """A line whose first non-whitespace characters are '%%' is a comment
    (lemur 0.0.2). Verbatim block bodies ('::' code, ':: math') are exempt,
    which is handled by their consumers, not here."""
    return text.lstrip(" \t").startswith("%%")


def load_lines(path: str, _stack: Optional[list[str]] = None) -> list[Line]:
    """Read a file and recursively resolve '!include' directives.

    Includes are resolved relative to the including file. Cycles are detected
    via the include stack rather than a global 'seen' set, so diamond-shaped
    includes (same file included from two places) remain legal.
    """
    stack = _stack or []
    apath = os.path.abspath(path)
    if apath in stack:
        chain = " -> ".join(stack + [apath])
        raise LemurError(f"circular include: {chain}", path, 0)
    try:
        with open(path, "r", encoding="utf-8") as fh:
            raw = fh.read().splitlines()
    except OSError as exc:
        raise LemurError(f"cannot read file: {exc}", path, 0) from exc

    out: list[Line] = []
    for no, text in enumerate(raw, start=1):
        m = re.match(r"^\s*!include\s+(\S+)\s*$", text)
        if m:
            target = os.path.join(os.path.dirname(path), m.group(1))
            out.extend(load_lines(target, stack + [apath]))
        else:
            out.append(Line(path, no, text))
    return out


# --------------------------------------------------------------------------
# document model
# --------------------------------------------------------------------------


@dataclass
class Block:
    kind: str  # heading|para|list|code|math|table|image|notes|annotate|bib|
    #            columns|stack|connect|spacer|env|style
    data: dict = field(default_factory=dict)
    step: int = 0  # activation step: 0 = base (visible immediately), n>0 later
    when: Optional[str] = None  # overlay spec ('2-4'); overrides step if set


@dataclass
class Slide:
    title: str = ""
    ref: Optional[str] = None
    kind: str = "content"  # content|section|title
    blocks: list[Block] = field(default_factory=list)
    sid: str = ""  # html id
    styles: list = field(default_factory=list)  # extra css classes ('.name')


@dataclass
class Deck:
    meta: dict = field(default_factory=dict)
    groups: list[list[Slide]] = field(default_factory=list)  # horiz -> vert
    refs: dict = field(default_factory=dict)  # name -> (slide_id, label, kind)
    bib_order: list[str] = field(default_factory=list)


# --------------------------------------------------------------------------
# parser
# --------------------------------------------------------------------------

# A directive may carry an attached option bracket, with no whitespace, right
# after its name: '[...]' for options (style classes) or '<...>' for an overlay
# spec (e.g. '!layer<2->'). group(2) is that bracket (incl. delimiters);
# group(3) is the remaining argument. Requiring no space keeps titles that start
# with '[' unambiguous and makes the bracket trivial to scan.
RE_DIRECTIVE = re.compile(r"^!(\w+)(\[[^\]]*\]|<[^>]*>)?(?:[ \t]+(.*))?$")
# code fence: ':: lang[lines] ^ref'. The line-highlight bracket attaches to the
# language with no space (unified bracket rule).
RE_CODE = re.compile(r"^::[ \t]*([\w+.-]*)(?:\[([^\]]+)\])?"
                     r"[ \t]*(?:\^([\w-]+))?[ \t]*$")
# annotation line: 'name[color/style]: label'. The option bracket attaches to
# the name with no space.
RE_ANNOTATION = re.compile(r"^([\w-]+)(?:\[([^\]]+)\])?"
                           r"[ \t]*(?::[ \t]*(.*))?$")
# connector line inside '!connect': '<from> <glyph> <to> [color/style]'. The
# glyph gives direction ('->' fwd, '<-' back, '<->' both, '--' plain line); the
# trailing option bracket holds a color and/or style keywords.
RE_CONNECT = re.compile(r"^([\w-]+)[ \t]*(<->|->|<-|--)[ \t]*([\w-]+)"
                        r"(?:[ \t]*\[([^\]]*)\])?[ \t]*$")
CONNECT_DIR = {"->": "fwd", "<-": "back", "<->": "both", "--": "none"}
# heading: '#[.style] Title'. An optional option bracket attaches to the marker.
RE_HEADING = re.compile(r"^(#{1,4})(\[[^\]]*\])?[ \t]+(.*?)$")
# a ref name is letters/digits/'_'/'-' (spec §Highlighting) — the same class as a
# mark; punctuation (':', '.', ',') terminates it, so 'see @jonas2010:' resolves.
RE_REFSUFFIX = re.compile(r"[ \t]+\^([\w-]+)[ \t]*$")
RE_BIBDEF = re.compile(r"^\^([\w-]+):[ \t]+(.*)$")
# list item: '-'/'*' static bullet, '+' incremental bullet, 'N.' ordered. A
# marker needs a trailing space, so '**bold**' at line start is not a bullet.
RE_LISTITEM = re.compile(r"^(\s*)([-+*]|\d+\.)(<[^>]*>)?[ \t]+(.*)$")
# an overlay spec: comma-separated 'n' / 'n-' / '-n' / 'n-m' terms
RE_OVERLAY_SPEC = re.compile(r"[\d,-]+")
# a '!gap' length: a number with an optional css unit
RE_GAP_SIZE = re.compile(r"[\d.]+(px|em|rem|ex|ch|vh|vw|%)?")

META_KEYS = {"title", "subtitle", "author", "date", "theme", "transition",
             "aspect", "institute", "titleimage",
             "header", "footer", "slidenumbers", "logo", "progress"}

# Semantic environments: a fixed, curated set the parser knows (no user-defined
# environments — that macro system is deliberately out of scope). Each is a
# '!<name> [Title] [^ref]' block with an indentation-delimited body of any
# blocks (including nested environments). The AST carries one neutral 'env' node
# parameterised by 'kind'; an emitter maps it (LaTeX '\begin{kind}', an html box).
SEMANTIC_ENVS = {"theorem", "lemma", "corollary", "proposition", "definition",
                 "proof", "example", "remark", "intuition", "note", "warning",
                 "exercise", "historical"}


def styles_from_bracket(bracket: Optional[str]) -> list:
    r"""Parse a leading option bracket into per-slide style classes.

    '!slide[.hero .plain] Title' passes '[.hero .plain]' here and gets back
    ['hero', 'plain']. Tokens are whitespace-separated; a '.name' token is a css
    class on the slide section, so a theme (or base.css) can restyle just that
    slide. Non-class tokens (and a '<...>' overlay bracket landing here by
    mistake) are ignored, leaving room for other option kinds later."""
    if not bracket or bracket[0] != "[":
        return []
    return [tok[1:] for tok in bracket[1:-1].split() if tok.startswith(".")]


def parse_style(spec: Optional[str]) -> dict:
    """Parse a style attribute (a span's '{…}', a '!style'/'!columns'/'!column'
    '[…]') into a neutral style dict. One rule everywhere: '.name' is a named
    style (built-in like '.bold'/'.center'/'.frame' or your own '.yeehaa'),
    '#rrggbb'/css-name is a foreground 'color', and 'bg:…' a background. Names
    and colour hints only — no css, no pixels — so the emitter realises them
    (html classes + inline style; LaTeX \\textcolor/\\colorbox/macros). Empty
    keys are omitted."""
    classes, color, bg = [], None, None
    for tok in (spec or "").split():
        if tok.startswith(".") and len(tok) > 1:
            classes.append(tok[1:])
        elif tok.startswith("bg:") and len(tok) > 3:
            bg = tok[3:]
        elif tok:
            color = tok                 # '#rrggbb' or a css colour name
    out: dict = {}
    if classes:
        out["classes"] = classes
    if color:
        out["color"] = color
    if bg:
        out["bg"] = bg
    return out


def parse_ann_style(spec: Optional[str]) -> tuple[Optional[str], list[str]]:
    """An annotation/connector bracket as (color, style-names): the same dotted
    vocabulary as a span — '.bold'/'.dashed'/… are style names, '#c0392b' the
    colour. Returns the color and the class names (annotate maps them to a
    step-gated highlight; connect to the arrow's line style)."""
    st = parse_style(spec)
    return st.get("color"), st.get("classes", [])


parse_connect_style = parse_ann_style   # same (color, style-names) shape


def split_ref(text: str) -> tuple[str, Optional[str]]:
    """Split a trailing '^ref' off a title string."""
    m = RE_REFSUFFIX.search(text)
    if m:
        return text[: m.start()].strip(), m.group(1)
    if text.startswith("^") and " " not in text:
        return "", text[1:]
    return text.strip(), None


class Parser:
    def __init__(self, lines: list[Line]):
        self.lines = lines
        self.i = 0
        self.deck = Deck()
        self.slide: Optional[Slide] = None
        # The activation (step) model (Plan.md Section 4.3). One monotonic
        # counter per slide. 'base_step' is the step at which plain content
        # currently appears (raised by '!pause'); 'max_step' is the highest
        # step allocated so far. Incremental elements ('+' items, extra image
        # layers, annotations) each take a fresh step above everything so far.
        self.base_step = 0
        self.max_step = 0
        self._slide_marks: set = set()  # mark names on the current slide (unique)
        self._sid_counter = 0
        self._bib_counter = 0
        # '!when' blocks: an indentation-delimited stack (like environments), each
        # {'indent', 'spec'}. Every block in the body is gated by the innermost
        # open spec; a dedent past a '!when' opener closes it. Nesting narrows.
        self.when_stack: list = []
        # One unified, nestable stack of open containers: environments
        # ('!theorem' …), styled blocks ('!style'), and the layout containers
        # '!columns'/'!column' and '!stack'/'!layer'. Each entry is
        # {'kind', 'indent', …}. Content-accepting kinds (env, style, column,
        # layer) carry a 'blocks' list that add() routes into; structural kinds
        # (columns, stack) carry only their 'block' and accept nothing but their
        # own children (a '!column'/'!layer'). A dedent past an entry's opener
        # indent closes it (the main loop), so all of them nest with one
        # machinery — a stack inside a column, columns inside a layer, etc.
        self.container_stack: list = []

    def alloc_step(self) -> int:
        """Allocate the next activation step (for an incremental element)."""
        self.max_step += 1
        return self.max_step

    def resolve_spec(self, spec: str, ln: Line) -> str:
        """Resolve/validate an overlay spec. A *relative* '+' allocates the next
        auto-step and shows only during it; '+-' allocates one and shows from it
        onward (like a '+' item) — so the author never writes step numbers. Any
        other spec must be a literal overlay ('2', '2-', '-3', '2-4', '2,4')."""
        if spec == "+":
            return str(self.alloc_step())
        if spec == "+-":
            return f"{self.alloc_step()}-"
        if RE_OVERLAY_SPEC.fullmatch(spec):
            return spec
        raise self.err(f"invalid overlay spec {spec!r}; use e.g. '2', '2-', "
                       "'-3', '2-4', '2,4', or the relative '+' / '+-'", ln)

    def resolve_relative(self, text: str) -> str:
        r"""Rewrite inline relative overlay suffixes on a span — ']<+>' / ']<+->'
        (after an optional '{style}'/'^name') — to concrete ']<N>' / ']<N->' by
        allocating a fresh auto-step for each, left to right. Code spans (`…`) and
        inline math ($…$) are skipped so a literal '<+' inside them is untouched.
        Runs during the scan, where the per-slide step counter is in order."""
        if "<+" not in text:
            return text
        out: list[str] = []
        i, n = 0, len(text)
        while i < n:
            c = text[i]
            if c == "\\" and i + 1 < n:
                out.append(text[i:i + 2]); i += 2; continue
            if c == "`":                       # skip a code span
                j = text.find("`", i + 1)
                j = j if j >= 0 else n - 1
                out.append(text[i:j + 1]); i = j + 1; continue
            if c == "$":                       # skip inline math ('\$' escaped)
                j, k = i + 1, i + 1
                while k < n and not (text[k] == "$" and text[k - 1] != "\\"):
                    k += 1
                out.append(text[i:k + 1]); i = k + 1; continue
            if c == "]":
                m = RE_REL_SUFFIX.match(text, i + 1)
                if m:
                    step = self.alloc_step()
                    spec = f"{step}-" if m.group(2) else str(step)
                    out.append("]" + m.group(1) + "<" + spec + ">")
                    i = m.end(); continue
            out.append(c); i += 1
        return "".join(out)

    def check_marks(self, marks: list, ln: Line) -> None:
        r"""Warn (do not fail) when a mark name repeats on a slide. Reusing a
        name is a *feature*: the occurrences form a group that shares a colour,
        one annotation label's arrow fans out to each, and '!connect' pairs each
        occurrence with its nearest counterpart. But an accidental reuse is
        usually a typo, so emit a weak guard. Names reset per slide, so the same
        name on another slide is unrelated."""
        for m in marks:
            if m["name"] in self._slide_marks:
                print(f"lemur: warning: {ln.file}:{ln.no}: mark '{m['name']}' "
                      "reused on this slide; the occurrences are grouped (shared "
                      "colour/arrows). Rename one if that was unintended.",
                      file=sys.stderr)
            self._slide_marks.add(m["name"])

    # -- low level ---------------------------------------------------------

    def peek(self) -> Optional[Line]:
        return self.lines[self.i] if self.i < len(self.lines) else None

    def _peek_content(self) -> Optional[Line]:
        """The next non-blank, non-comment line (not consumed), or None."""
        for ln in self.lines[self.i:]:
            if not ln.blank and not is_comment(ln.text):
                return ln
        return None

    def next(self) -> Line:
        ln = self.lines[self.i]
        self.i += 1
        return ln

    def err(self, msg: str, ln: Line) -> LemurError:
        return LemurError(msg, ln.file, ln.no)

    def collect_indented(self, opener: Line) -> list[str]:
        """Collect the indented body following a block opener ('::',
        '!notes', '!annotate').

        The first body line defines the block's indentation: its exact
        leading whitespace becomes the required prefix of every further body
        line. Lemur deliberately fixes no tab width; tabs or spaces are the
        author's choice per block, but must be consistent within one block.
        Blank lines are kept when further body follows. A non-blank line
        that is indented relative to the opener but does not start with the
        prefix raises an error rather than silently ending the block, since
        it is almost certainly a typo. Deeper indentation (prefix plus more
        whitespace) is content and preserved, e.g. nested code.
        """
        opener_ws = leading_ws(opener.text)
        prefix: Optional[str] = None
        body: list[str] = []
        pending = 0
        while (ln := self.peek()) is not None:
            if ln.blank:
                pending += 1
                self.next()
                continue
            ws = leading_ws(ln.text)
            deeper = ws.startswith(opener_ws) and len(ws) > len(opener_ws)
            if prefix is None:
                if not deeper:
                    break
                prefix = ws
            if ln.text.startswith(prefix):
                if body:  # blanks between opener and first line are dropped
                    body.extend([""] * pending)
                pending = 0
                body.append(ln.text[len(prefix):])
                self.next()
            elif deeper:
                raise self.err(
                    "inconsistent indentation in block body: every line "
                    "must start with the same leading whitespace as the "
                    "block's first line", ln)
            else:
                break
        return body

    def check_math(self, text: str, ln: Line) -> None:
        """Parse-time diagnostics for inline math delimiters (single '$'
        since lemur 0.0.2). These are warnings, not errors: rendering
        proceeds either way, and even-count false positives (two unescaped
        currency dollars) are undetectable in principle."""
        t = re.sub(r"`[^`]*`", "", text)  # code spans are verbatim
        if "$$" in t:
            print(f"lemur: warning: {ln.file}:{ln.no}: found '$$'; inline "
                  "math uses a single '$' since lemur 0.0.2 (escape literal "
                  "dollars as '\\$')", file=sys.stderr)
        t = re.sub(r"\\\$", "", t)
        if t.count("$") % 2:
            print(f"lemur: warning: {ln.file}:{ln.no}: unbalanced '$'; "
                  "escape literal dollars as '\\$'", file=sys.stderr)

    # -- structure ---------------------------------------------------------

    def new_slide(self, title: str, ref: Optional[str], kind: str,
                  styles: Optional[list] = None) -> None:
        self._sid_counter += 1
        slug = re.sub(r"[^\w-]+", "-", title.lower()).strip("-") or "slide"
        sid = ref or f"{slug}-{self._sid_counter}"
        self.slide = Slide(title=title, ref=ref, kind=kind, sid=sid,
                           styles=styles or [])
        self.base_step = 0
        self.max_step = 0
        self._slide_marks = set()     # mark names reset per slide
        self.container_stack = []     # containers don't cross slides
        self.when_stack = []          # nor do '!when' blocks
        self.deck.groups.append([self.slide])
        if ref:
            self.register_ref(ref, sid, title or "slide", "slide", None)

    def register_ref(self, name: str, sid: str, label: str, kind: str,
                     ln: Optional[Line]) -> None:
        if name in self.deck.refs:
            prev = self.deck.refs[name]
            where = f"{ln.file}:{ln.no}" if ln else "?"
            print(f"lemur: warning: reference '^{name}' redefined at {where} "
                  f"(was {prev[2]})", file=sys.stderr)
        self.deck.refs[name] = (sid, label, kind)

    def add(self, block: Block, ln: Line) -> None:
        if self.slide is None:
            raise self.err("content outside of a slide; start one with "
                           "'!slide' or '# Section'", ln)
        block.step = self.base_step
        # the innermost open '!when' block gates this block (nesting narrows)
        if self.when_stack:
            block.when = self.when_stack[-1]["spec"]
        # content routes to the innermost open container (env/style/column/layer),
        # else the slide (see _content_target)
        self._content_target(ln).append(block)

    def _content_target(self, ln: Line) -> list:
        """The block list the next block belongs to: the innermost open
        content-accepting container, else the slide. A structural container
        ('!columns'/'!stack') cannot hold content directly — only its children
        ('!column'/'!layer') can — so content there is an error."""
        if self.container_stack:
            top = self.container_stack[-1]
            if "blocks" in top:
                return top["blocks"]
            child = "column" if top["kind"] == "columns" else "layer"
            raise self.err(f"content directly inside '!{top['kind']}' is not "
                           f"allowed; put it in a '!{child}'", ln)
        return self.slide.blocks

    def start_columns(self, bracket: Optional[str], arg: str,
                      ln: Line) -> None:
        """Begin a '!columns[60 40 .boxed]' block. In the bracket a numeric token
        is a relative column width (any number of columns; missing widths default
        to equal flex) and everything else is a style attribute (classes/colour/
        bg) applied to the container. Indentation-delimited: a dedent ends it
        (the main loop); '!column' delimits the columns within, and the per-slide
        step counter flows across columns so a '!pause' in one defers what
        follows. Nests freely — inside a column, a layer, or an environment
        (item 5)."""
        if arg:
            raise self.err("'!columns' widths go in a bracket: "
                           "'!columns[60 40]'", ln)
        widths: list[float] = []
        style_toks: list[str] = []
        spec = bracket[1:-1] if bracket and bracket[0] == "[" else ""
        for tok in spec.replace(",", " ").split():
            try:
                widths.append(float(tok))     # a numeric token is a width
            except ValueError:
                style_toks.append(tok)        # everything else styles the block
        block = Block("columns", {"widths": widths,
                                  "style": parse_style(" ".join(style_toks)),
                                  "columns": []})
        self.add(block, ln)           # into the current container (or the slide)
        self.container_stack.append({"kind": "columns", "block": block,
                                     "indent": ln.indent})

    def start_column(self, bracket: Optional[str], arg: str, ln: Line) -> None:
        """Begin a '!column[.center]' within the enclosing '!columns' block. Its
        content is indented under it (item 5). The bracket is a style attribute;
        the built-in classes '.center'/'.bottom' set the vertical alignment
        ('.top' is the default), and any other '.class'/colour styles the column."""
        top = self.container_stack[-1] if self.container_stack else None
        if top is None or top["kind"] != "columns":
            raise self.err("'!column' outside of a '!columns' block", ln)
        if arg:
            raise self.err("'!column' options go in a bracket: '!column[.center]'",
                           ln)
        style = parse_style(bracket[1:-1]) if bracket and bracket[0] == "[" \
            else {}
        col: dict = {"blocks": [], "style": style}
        top["block"].data["columns"].append(col)
        self.container_stack.append({"kind": "column", "blocks": col["blocks"],
                                     "indent": ln.indent})

    def start_stack(self, ln: Line) -> None:
        """Begin a '!stack' block: its '!layer' children overlap in one grid
        cell, so successive layers 'take the place of' one another instead of
        stacking vertically (item 4). Indentation-delimited like '!columns'; a
        dedent ends it, and the per-slide step counter keeps flowing across
        layers. Every layer must carry an explicit overlay spec, so nothing shows
        until asked. Nests freely — inside a column, a layer, or an environment."""
        block = Block("stack", {"layers": []})
        self.add(block, ln)           # into the current container (or the slide)
        self.container_stack.append({"kind": "stack", "block": block,
                                     "indent": ln.indent})

    def start_layer(self, bracket: Optional[str], arg: str, ln: Line) -> None:
        """Begin a '!layer<spec>' within the enclosing '!stack'. The overlay spec
        is mandatory (item 4) and gives the layer its 'when to show' — the same
        attached '<…>' bracket as '!when' and list-item '+<spec>'."""
        top = self.container_stack[-1] if self.container_stack else None
        if top is None or top["kind"] != "stack":
            raise self.err("'!layer' outside of a '!stack' block", ln)
        spec = bracket[1:-1].strip() if bracket and bracket[0] == "<" else ""
        if not spec:
            raise self.err("'!layer' needs an overlay spec in angle brackets, "
                           "e.g. '!layer<2>' or '!layer<2->'; layers never show "
                           "on their own", ln)
        if not RE_OVERLAY_SPEC.fullmatch(spec):
            raise self.err(f"invalid '!layer' spec {spec!r}; use e.g. '<2>', "
                           "'<2->', '<-3>', '<2-4>' or '<2,4>'", ln)
        layer: dict = {"blocks": [], "when": spec}
        top["block"].data["layers"].append(layer)
        self.container_stack.append({"kind": "layer", "blocks": layer["blocks"],
                                     "indent": ln.indent})

    def start_env(self, kind: str, arg: str, ln: Line) -> None:
        """Begin a semantic environment ('!theorem', '!proof', …). The argument
        is an optional title with an optional trailing '^ref'. The body is
        indentation-delimited (like '!columns'/'!stack'): everything indented
        past this line is the body — any blocks, including nested environments —
        and a dedent to this indent or less ends it. The block is added to the
        current innermost container, so it can nest inside another env, a column
        or a layer."""
        title, ref = split_ref(arg)
        block = Block("env", {"kind": kind, "title": title or None, "ref": ref,
                              "blocks": []})
        self.add(block, ln)           # routes into the current container
        self.container_stack.append({"kind": "env", "block": block,
                               "indent": ln.indent, "blocks": block.data["blocks"]})
        if ref:
            self.register_ref(ref, self.slide.sid, title or kind, kind, ln)

    def start_style(self, bracket: Optional[str], arg: str, ln: Line) -> None:
        """Begin a '!style[.class #color bg:… bold]' styled block. The option
        bracket carries the style attribute (same vocabulary as an inline span);
        the body is indentation-delimited like an environment. A styled block is
        purely visual (the emitter renders the style) — no semantic label. Its
        built-in classes include '.frame' (draw a box) and '.center'. An optional
        '^ref' after the bracket labels it for cross-reference."""
        style = parse_style(bracket[1:-1]) if bracket and bracket[0] == "[" \
            else {}
        _, ref = split_ref(arg)
        block = Block("style", {"style": style, "ref": ref, "blocks": []})
        self.add(block, ln)           # routes into the current container
        self.container_stack.append({"kind": "style", "block": block,
                                     "indent": ln.indent, "blocks": block.data["blocks"]})
        if ref:
            self.register_ref(ref, self.slide.sid, "style", "style", ln)

    # -- main loop ---------------------------------------------------------

    def parse(self) -> Deck:
        while (ln := self.peek()) is not None:
            if ln.blank or is_comment(ln.text):
                self.next()
                continue
            # indentation-delimited blocks (columns/columns' columns, stacks/
            # layers, environments, styled blocks, '!when') end when a non-blank
            # line dedents to the opener's indent or less — no end marker (items
            # 4, 5). Close the innermost scopes first; one uniform stack now holds
            # every container, so nested layouts close in the right order.
            while self.container_stack and ln.indent <= self.container_stack[-1]["indent"]:
                self.container_stack.pop()
            while self.when_stack and ln.indent <= self.when_stack[-1]["indent"]:
                self.when_stack.pop()
            s = ln.stripped

            if (m := RE_CODE.match(s)):
                self.parse_code(m, self.next())
            elif (m := RE_DIRECTIVE.match(s)):
                self.parse_directive(m, self.next())
            elif (m := RE_HEADING.match(s)):
                self.parse_heading(m, self.next())
            elif RE_BIBDEF.match(s):
                self.parse_bib()
            elif RE_LISTITEM.match(ln.text):
                self.parse_list()
            else:
                self.parse_paragraph()
        return self.deck

    # -- constructs --------------------------------------------------------

    def parse_heading(self, m: re.Match, ln: Line) -> None:
        level = len(m.group(1))
        styles = styles_from_bracket(m.group(2))
        title, ref = split_ref(m.group(3))
        self.check_math(title, ln)
        if level == 1:
            self.new_slide(title, ref, "section", styles)
        elif level == 2 and self.slide is None:
            # convenience: '##' before any slide behaves like '!slide'
            self.new_slide(title, ref, "content", styles)
        else:
            self.add(Block("heading", {"level": level,
                                       "text": self.resolve_relative(title),
                                       "ref": ref}), ln)
            if ref and self.slide:
                self.register_ref(ref, self.slide.sid, title, "heading", ln)

    def parse_directive(self, m: re.Match, ln: Line) -> None:
        # group(2) is an attached option bracket ('[...]' or '<...>'), group(3)
        # the remaining argument (see RE_DIRECTIVE).
        name, bracket, arg = m.group(1), m.group(2), (m.group(3) or "").strip()
        if name in META_KEYS and self.slide is None:
            self.deck.meta[name] = arg
        elif name == "slide":
            title, ref = split_ref(arg)
            self.new_slide(title, ref, "content", styles_from_bracket(bracket))
        elif name == "pause":
            if self.slide is None:
                raise self.err("'!pause' outside of a slide", ln)
            # everything after this pause appears together on the next step
            self.base_step = self.alloc_step()
        elif name == "notes":
            body = [b for b in self.collect_indented(ln)
                    if not is_comment(b)]
            if not body:
                raise self.err("'!notes' without an indented body", ln)
            self.add(Block("notes", {"text": "\n".join(body)}), ln)
        elif name == "annotate":
            body = self.collect_indented(ln)
            items = []
            for raw in body:
                if not raw.strip() or is_comment(raw):
                    continue
                am = RE_ANNOTATION.match(raw.strip())
                if not am:
                    raise self.err(
                        f"cannot parse annotation {raw.strip()!r}; expected "
                        "'name [color]: label text'", ln)
                self.check_math(am.group(3) or "", ln)
                # each annotation line is its own step: the anchor colors and/or
                # emphasises, and (if it has a label) a labelled arrow appears,
                # together on that keypress, cumulatively. The bracket holds a
                # color and/or style keywords (bold/italic/underline).
                color, styles = parse_ann_style(am.group(2))
                items.append({"name": am.group(1), "color": color,
                              "styles": styles, "text": am.group(3) or "",
                              "step": self.alloc_step()})
            if not items:
                raise self.err("'!annotate' without an indented body of "
                               "'name [color]: text' lines", ln)
            self.add(Block("annotate", {"items": items}), ln)
        elif name == "connect":
            body = self.collect_indented(ln)
            links = []
            for raw in body:
                if not raw.strip() or is_comment(raw):
                    continue
                cm = RE_CONNECT.match(raw.strip())
                if not cm:
                    raise self.err(
                        f"cannot parse connector {raw.strip()!r}; expected "
                        "'from -> to [color .style]' (arrows: -> <- <-> --)", ln)
                color, styles = parse_connect_style(cm.group(4))
                # each connector is its own step: the arrow appears on that
                # keypress and stays, cumulatively (like an annotate line)
                links.append({"from": cm.group(1), "to": cm.group(3),
                              "dir": CONNECT_DIR[cm.group(2)], "color": color,
                              "styles": styles, "step": self.alloc_step()})
            if not links:
                raise self.err("'!connect' without an indented body of "
                               "'from -> to' lines", ln)
            self.add(Block("connect", {"links": links}), ln)
        elif name == "gap":
            # vertical space: '!gap' (default), '!gap[2em]' (a fixed length) or
            # '!gap[fill]' (grows to push content apart). Slide-only presentation
            # intent; a manuscript emitter drops it.
            if arg:
                raise self.err("'!gap' size goes in a bracket: '!gap[2em]' or "
                               "'!gap[fill]'", ln)
            size = bracket[1:-1].strip().lower() if bracket and bracket[0] == "[" \
                else ""
            if size and size != "fill" and not RE_GAP_SIZE.fullmatch(size):
                raise self.err(f"invalid '!gap' size {size!r}; use e.g. '[2em]', "
                               "'[fill]', or nothing", ln)
            self.add(Block("spacer", {"size": size or None}), ln)
        elif name == "table":
            self.parse_table(arg, ln)
        elif name == "img":
            self.parse_image(arg, ln)
        elif name == "anim":
            self.parse_anim(arg, ln)
        elif name == "shader":
            self.parse_shader(arg, ln)
        elif name == "plot":
            self.parse_plot(arg, ln)
        elif name == "columns":
            self.start_columns(bracket, arg, ln)
        elif name == "column":
            self.start_column(bracket, arg, ln)
        elif name == "stack":
            self.start_stack(ln)
        elif name == "layer":
            self.start_layer(bracket, arg, ln)
        elif name == "style":
            self.start_style(bracket, arg, ln)
        elif name == "when":
            # '!when<spec>' opens an indentation-delimited block: every block in
            # its body shows only while the step matches the overlay spec (e.g.
            # '<2>', '<2->', '<2-4>', or the relative '<+>' / '<+->') — the same
            # '<…>' bracket as '!layer' and '+<…>'. A dedent ends it; '!when'
            # blocks nest (narrow).
            spec = bracket[1:-1].strip() if bracket and bracket[0] == "<" else ""
            if not spec:
                raise self.err("'!when' needs an overlay spec in angle brackets, "
                               "e.g. '!when<2->', '!when<2-4>' or '!when<+->'", ln)
            spec = self.resolve_spec(spec, ln)   # '+'/'+-' -> a concrete step
            nxt = self._peek_content()
            if nxt is None or nxt.indent <= ln.indent:
                raise self.err("'!when' needs an indented body — the blocks to "
                               "gate go on the following lines, indented under "
                               "it (like a table or '!columns')", ln)
            self.when_stack.append({"indent": ln.indent, "spec": spec})
        elif name in SEMANTIC_ENVS:
            self.start_env(name, arg, ln)
        else:
            raise self.err(f"unknown directive '!{name}'", ln)

    def parse_code(self, m: re.Match, ln: Line) -> None:
        lang, lines_spec, ref = m.group(1), m.group(2), m.group(3)
        body = self.collect_indented(ln)
        text = "\n".join(body)
        if lang == "math":
            # display math can be an arrow target; keep the TeX raw and record
            # where the '\mk' anchors are (the bridge re-injects the class)
            try:
                tex, marks = extract_marks(text)
            except ValueError as exc:
                raise self.err(str(exc), ln) from exc
            self.check_marks(marks, ln)
            data: dict = {"tex": tex, "ref": ref}
            if marks:
                data["marks"] = marks
            self.add(Block("math", data), ln)
        else:
            # each '|'-separated line-highlight group is its own step, in
            # document order; the code appears at the block's base step and the
            # groups highlight progressively (item 5)
            highlights: dict[int, list[int]] = {}
            if lines_spec:
                for grp in lines_spec.split("|"):
                    highlights[self.alloc_step()] = parse_line_ranges(grp)
            self.add(Block("code", {"lang": lang, "text": text, "ref": ref,
                                    "lines": lines_spec,
                                    "highlights": highlights}), ln)
        if ref and self.slide:
            self.register_ref(ref, self.slide.sid, lang or "code", "code", ln)

    def parse_list(self) -> None:
        first = self.peek()
        # each item: (ws, text, ordered, step, when). A running step counter
        # flows through the items in document order: '+' advances it (a fresh
        # step), while '-'/'*'/'N.' sit at the current value — so an item inherits
        # the step of the previous thing shown, and a nested item (which follows
        # its parent in reading order) inherits the parent's step. 'when' is an
        # explicit overlay spec from '+<2-4>'/'-<2>' which overrides the step; a
        # spec'd '+' does not auto-advance. ws drives the nesting.
        items: list[tuple] = []
        cur = self.base_step          # the running activation step for this list
        while (ln := self.peek()) is not None and not ln.blank:
            if is_comment(ln.text):
                self.next()
                continue
            m = RE_LISTITEM.match(ln.text)
            if not m:
                break
            self.next()
            ws, marker, spec, text = m.group(1), m.group(2), m.group(3), \
                m.group(4)
            when = self.resolve_spec(spec[1:-1].strip(), ln) if spec else None
            # continuation lines: indented deeper than the item's marker
            while (nl := self.peek()) is not None and not nl.blank \
                    and not RE_LISTITEM.match(nl.text):
                if is_comment(nl.text):
                    self.next()
                    continue
                nws = leading_ws(nl.text)
                if not (nws.startswith(ws) and len(nws) > len(ws)):
                    break
                text += " " + self.next().stripped
            ordered = marker not in ("-", "+", "*")
            if marker == "+" and not when:
                cur = self.alloc_step()   # '+' advances the running step
            text = self.resolve_relative(text)   # inline '<+>' after the item step
            self.check_math(text, ln)
            items.append((ws, text, ordered, cur, when))
        self.add(Block("list", {"items": items}), first)

    def parse_paragraph(self) -> None:
        first = self.peek()
        parts = []
        while (ln := self.peek()) is not None and not ln.blank:
            s = ln.stripped
            if is_comment(ln.text):
                self.next()  # comments do not interrupt a paragraph
                continue
            # a continuation line that dedents to/under the innermost open
            # container's opener ends the paragraph, so it never straddles a
            # container boundary (columns/layers/environments; items 4, 5)
            if parts and self.container_stack \
                    and ln.indent <= self.container_stack[-1]["indent"]:
                break
            if RE_DIRECTIVE.match(s) or RE_CODE.match(s) \
                    or RE_HEADING.match(s) or RE_LISTITEM.match(ln.text) \
                    or RE_BIBDEF.match(s):
                break
            if s.startswith(r"\%%"):  # escaped literal %% at line start
                s = s[1:]
            self.next()
            parts.append(s)
        if parts:
            text = self.resolve_relative(" ".join(parts))   # inline '<+>'
            self.check_math(text, first)
            self.add(Block("para", {"text": text}), first)
        else:  # defensive: avoid an infinite loop on unhandled input
            raise self.err(f"cannot parse line: {first.text!r}", first)

    def parse_bib(self) -> None:
        first = self.peek()
        entries = []
        while (ln := self.peek()) is not None and not ln.blank:
            if is_comment(ln.text):
                self.next()
                continue
            m = RE_BIBDEF.match(ln.stripped)
            if not m:
                break
            self.next()
            key, text = m.group(1), m.group(2)
            url = None
            um = re.match(r"^<(\S+)>$", text.strip())
            if um:
                url = um.group(1)
                self.deck.refs[key] = (None, url, "url")
            else:
                self._bib_counter += 1
                self.deck.bib_order.append(key)
                sid = self.slide.sid if self.slide else None
                self.deck.refs[key] = (sid, str(self._bib_counter), "bib")
            entries.append({"key": key, "text": text, "url": url})
        # url-only definitions produce no visible output
        visible = [e for e in entries if e["url"] is None]
        if visible and self.slide is not None:
            self.add(Block("bib", {"entries": visible}), first)

    # -- tables ------------------------------------------------------------

    def parse_table(self, arg: str, ln: Line) -> None:
        title, ref = split_ref(arg)
        cols: list[dict] = []
        seps: list[str] = []
        caption = ""
        header = True                # '!noheader' suppresses the heading row
        rows: list = []  # list of cell-lists or 'sep-strong'/'sep-light'
        base = ln.indent

        while (nl := self.peek()) is not None:
            if nl.blank:
                self.next()
                # a blank line ends the table only if nothing indented follows
                nxt = self.peek()
                if nxt is None or nxt.indent <= base:
                    break
                continue
            if is_comment(nl.text):
                self.next()  # commented-out rows or notes within the table
                continue
            s = nl.stripped
            if (dm := RE_DIRECTIVE.match(s)):
                dname = dm.group(1)
                if dname == "cols":
                    self.next()
                    cols, seps = parse_cols((dm.group(3) or ""), nl)
                elif dname == "caption":
                    self.next()
                    caption = (dm.group(3) or "").strip()
                    while (cl := self.peek()) is not None and not cl.blank \
                            and not RE_DIRECTIVE.match(cl.stripped):
                        caption += " " + self.next().stripped
                    self.check_math(caption, nl)
                elif dname == "noheader":
                    self.next()
                    header = False
                else:
                    break  # next directive: table is done
            elif nl.indent > base:
                self.next()
                if re.fullmatch(r"=+", s):
                    rows.append("sep-strong")
                elif re.fullmatch(r"-+", s):
                    rows.append("sep-light")
                else:
                    cells = split_row(s, seps, nl)
                    # cells containing a separator character mis-split; the
                    # author chose the separators, so warn with the exact row
                    if cols and len(cells) != len(cols):
                        print(f"lemur: warning: {nl.file}:{nl.no}: table "
                              f"row has {len(cells)} cells, expected "
                              f"{len(cols)}; a separator inside a cell? "
                              "(pick other separators in '!cols' or rewrite "
                              "the cell)", file=sys.stderr)
                    self.check_math(s, nl)
                    rows.append(cells)
            else:
                break

        if not cols:
            raise self.err("'!table' without a '!cols' declaration", ln)
        self.add(Block("table", {"title": title, "ref": ref, "cols": cols,
                                 "caption": caption, "rows": rows,
                                 "header": header}), ln)
        if ref and self.slide:
            self.register_ref(ref, self.slide.sid, title or "table",
                              "table", ln)

    # -- images ------------------------------------------------------------

    def parse_image(self, arg: str, ln: Line) -> None:
        title, ref = split_ref(arg)
        img = {"title": title, "ref": ref, "srcs": [], "caption": "",
               "width": None, "height": None, "mode": "overlay"}
        while (nl := self.peek()) is not None:
            if nl.blank:
                self.next()
                continue
            if is_comment(nl.text):
                self.next()
                continue
            dm = RE_DIRECTIVE.match(nl.stripped)
            if not dm:
                break
            dname, darg = dm.group(1), (dm.group(3) or "").strip()
            if dname == "src":
                self.next()
                img["srcs"].append(darg)
            elif dname == "caption":
                self.next()
                img["caption"] = darg
                while (cl := self.peek()) is not None and not cl.blank \
                        and not RE_DIRECTIVE.match(cl.stripped):
                    img["caption"] += " " + self.next().stripped
                self.check_math(img["caption"], nl)
            elif dname in ("width", "height", "mode"):
                self.next()
                img[dname] = darg
            else:
                break
        if not img["srcs"]:
            raise self.err("'!img' without any '!src'", ln)
        self._finish_image(img, title, ref, ln)

    def parse_anim(self, arg: str, ln: "Line") -> None:
        """A build-time animation embedded in a viewport on the slide. `!src` is a
        Python animation module (lemur.anim / wanim-style); `!viewport` is where it
        renders — 'body' (default), 'full', or 'x y w h'. Its beats (`self.next()`)
        become the slide's steps, resolved when the emitter runs the module."""
        title, ref = split_ref(arg)
        anim = {"title": title, "ref": ref, "src": None, "viewport": "body",
                "width": None, "height": None}
        while (nl := self.peek()) is not None:
            if nl.blank or is_comment(nl.text):
                self.next()
                continue
            dm = RE_DIRECTIVE.match(nl.stripped)
            if not dm:
                break
            dname, darg = dm.group(1), (dm.group(3) or "").strip()
            if dname == "src":
                self.next()
                anim["src"] = darg
            elif dname in ("viewport", "width", "height"):
                self.next()
                anim[dname] = darg
            else:
                break
        if not anim["src"]:
            raise self.err("'!anim' without a '!src' (the animation .py)", ln)
        self.add(Block("anim", anim), ln)
        if ref and self.slide:
            self.register_ref(ref, self.slide.sid, title or "animation", "anim", ln)

    def parse_shader(self, arg: str, ln: "Line") -> None:
        """A live GPU shader on the slide: `!src` is a GLSL fragment shader
        (Shadertoy's `mainImage` convention), rendered in real time by the
        presenter. `!viewport` places it like an `!anim` ('body', 'full' — behind
        the slide's text — or 'x y w h'); `!steps N` gives it N steps of its own
        (the shader reads them as a smoothed `iStep`); `!sound <preset>` adds an
        optional generative soundtrack; `!quality` scales its resolution."""
        title, ref = split_ref(arg)
        sh = {"title": title, "ref": ref, "src": None, "viewport": "body", "width": None,
              "height": None, "steps": None, "sound": None, "quality": None}
        while (nl := self.peek()) is not None:
            if nl.blank or is_comment(nl.text):
                self.next()
                continue
            dm = RE_DIRECTIVE.match(nl.stripped)
            if not dm:
                break
            dname, darg = dm.group(1), (dm.group(3) or "").strip()
            if dname in ("src", "viewport", "width", "height", "sound", "quality"):
                self.next()
                sh[dname] = darg
            elif dname == "steps":
                self.next()
                if not darg.isdigit():
                    raise self.err("'!steps' takes a whole number, e.g. '!steps 3'", nl)
                sh["steps"] = int(darg)
            else:
                break
        if not sh["src"]:
            raise self.err("'!shader' without a '!src' (the GLSL fragment shader)", ln)
        self.add(Block("shader", sh), ln)
        if ref and self.slide:
            self.register_ref(ref, self.slide.sid, title or "shader", "shader", ln)

    def parse_plot(self, arg: str, ln: "Line") -> None:
        """A build-time figure from a matplotlib script. `!src` is a Python module
        that builds a Figure (a `figure()`/`plot()` function, a module `fig`, or
        the current pyplot figure); the emitter runs it and bakes the figure to a
        self-contained SVG, placed like `!img` (with `!caption`/`!width`)."""
        title, ref = split_ref(arg)
        plot = {"title": title, "ref": ref, "src": None, "caption": "",
                "width": None, "height": None}
        while (nl := self.peek()) is not None:
            if nl.blank or is_comment(nl.text):
                self.next()
                continue
            dm = RE_DIRECTIVE.match(nl.stripped)
            if not dm:
                break
            dname, darg = dm.group(1), (dm.group(3) or "").strip()
            if dname == "src":
                self.next()
                plot["src"] = darg
            elif dname == "caption":
                self.next()
                plot["caption"] = darg
                while (cl := self.peek()) is not None and not cl.blank \
                        and not RE_DIRECTIVE.match(cl.stripped):
                    plot["caption"] += " " + self.next().stripped
                self.check_math(plot["caption"], nl)
            elif dname in ("width", "height"):
                self.next()
                plot[dname] = darg
            else:
                break
        if not plot["src"]:
            raise self.err("'!plot' without a '!src' (the matplotlib .py)", ln)
        self.add(Block("plot", plot), ln)
        if ref and self.slide:
            self.register_ref(ref, self.slide.sid, title or "figure", "plot", ln)

    def _finish_image(self, img, title, ref, ln) -> None:
        if img["mode"] not in ("overlay", "replace"):
            raise self.err(f"invalid '!mode {img['mode']}' "
                           "(use 'overlay' or 'replace')", ln)
        # the base layer shows with the figure; each extra layer reveals on its
        # own step (Plan.md Section 4.3). Steps are allocated in document order.
        img["layer_steps"] = [self.alloc_step() for _ in img["srcs"][1:]]
        self.add(Block("image", img), ln)
        if ref and self.slide:
            self.register_ref(ref, self.slide.sid, title or "figure",
                              "image", ln)


def _is_col_sep(c: str) -> bool:
    """A '!cols' column separator is any single punctuation character — the
    author's choice (spec, 'How to use tables'). Alphanumerics and whitespace
    are name characters; '[' ']' '"' stay reserved for alignment brackets and
    quoting, so a header that must contain punctuation is written in quotes."""
    return not c.isalnum() and not c.isspace() and c not in '[]"'


def parse_cols(spec: str, ln: Line) -> tuple[list[dict], list[str]]:
    """Parse a '!cols' declaration into column descriptors and the separator
    sequence used to split data rows (README.lmr, 'How to use tables')."""
    cols: list[dict] = []
    seps: list[str] = []
    i, n = 0, len(spec)
    while i < n:
        while i < n and spec[i] in " \t":
            i += 1
        if i >= n:
            break
        if spec[i] == '"':
            i += 1
            name = []
            while i < n:
                if spec[i] == "\\" and i + 1 < n and spec[i + 1] == '"':
                    name.append('"')
                    i += 2
                elif spec[i] == '"':
                    i += 1
                    break
                else:
                    name.append(spec[i])
                    i += 1
            else:
                raise LemurError("unterminated quoted column name",
                                 ln.file, ln.no)
            name = "".join(name)
        else:
            j = i
            while j < n and spec[j] != "[" and not _is_col_sep(spec[j]):
                j += 1
            name = spec[i:j].strip()
            i = j
        align = None
        if i < n and spec[i] == "[":
            j = spec.find("]", i)
            if j < 0:
                raise LemurError("unterminated alignment bracket",
                                 ln.file, ln.no)
            align = spec[i + 1:j].strip()
            if align not in ("l", "r", "c"):
                raise LemurError(f"invalid alignment '[{align}]' "
                                 "(use l, r, or c)", ln.file, ln.no)
            i = j + 1
        while i < n and spec[i] in " \t":
            i += 1
        cols.append({"name": name, "align": align or "l"})
        if i < n:
            if _is_col_sep(spec[i]):
                seps.append(spec[i])
                i += 1
            else:
                raise LemurError(
                    f"expected a column separator but found {spec[i]!r} "
                    "(any punctuation may separate columns; quote a header "
                    'that contains punctuation, e.g. "P(x)")',
                    ln.file, ln.no)
    return cols, seps


def parse_line_ranges(spec: str) -> list[int]:
    """Parse one '|'-separated group of a code line-highlight spec into line
    numbers: '4-6' -> [4,5,6], '3,7' -> [3,7], '1' -> [1]. Invalid parts are
    skipped."""
    nums: list[int] = []
    for part in spec.split(","):
        part = part.strip()
        if "-" in part:
            a, _, b = part.partition("-")
            try:
                nums.extend(range(int(a), int(b) + 1))
            except ValueError:
                continue
        elif part:
            try:
                nums.append(int(part))
            except ValueError:
                continue
    return nums


def split_row(row: str, seps: list[str], ln: Line) -> list[str]:
    """Split a table data row using the same separator sequence as '!cols'."""
    cells = []
    rest = row
    for sep in seps:
        idx = rest.find(sep)
        if idx < 0:
            break
        cells.append(rest[:idx].strip())
        rest = rest[idx + 1:]
    cells.append(rest.strip())
    return cells


# --------------------------------------------------------------------------
# inline rendering
# --------------------------------------------------------------------------

RE_MARK_NAME = re.compile(r"[\w-]+")
# suffix after a '[content]' span, in order: an optional '{style}' attribute
# (how it looks), an optional '^name' (a mark), an optional '<spec>' (when it
# shows). Any one makes the brackets meaningful; none, and '[content]' stays
# literal. All compose: '[x]{.accent #c00}^m<2->'.
RE_SPAN_SUFFIX = re.compile(
    r"(?:\{([^}]*)\})?(?:\^([\w-]+))?(?:<([\d,-]+)>)?")
# a relative overlay suffix after a span's ']' (with any '{style}'/'^name'
# between): group(1) is that prefix, group(2) is '' ('<+>') or '-' ('<+->').
RE_REL_SUFFIX = re.compile(r"((?:\{[^}]*\})?(?:\^[\w-]+)?)<\+(-?)>")


def extract_marks(tex: str) -> tuple[str, list]:
    r"""Strip '\mk{name}{content}' mark anchors from a TeX string. Returns the
    *raw* TeX (renderer-neutral — no lemur/MathJax macros) and a list of marks
    {name, from, to} giving each mark's character span in the raw TeX. Nested
    '\mk' yields nested (contained) spans; escaped braces ('\{','\}') are not
    delimiters. Raises ValueError with a snippet on malformed input; the caller
    converts it into a located LemurError.

    The point is neutrality: the AST carries only the raw TeX and where the
    marks are. The DOM bridge re-injects '\htmlClass{lmr-a-name}{…}' at these
    offsets at render time (MathJax-specific); a LaTeX emitter injects its own;
    a plain emitter ignores them. See spec/display-contract.md / Plan-Latex.md.
    """
    out: list = []
    marks: list = []
    off = 0                          # length of the raw TeX emitted so far
    i, n = 0, len(tex)
    while i < n:
        j = tex.find(r"\mk{", i)
        if j < 0:
            out.append(tex[i:])
            break
        pre = tex[i:j]
        out.append(pre)
        off += len(pre)
        k = tex.find("}", j + 4)
        if k < 0:
            raise ValueError(r"unterminated '\mk{name}' near "
                             f"{tex[j:j+30]!r}")
        name = tex[j + 4:k]
        if not RE_MARK_NAME.fullmatch(name):
            raise ValueError(rf"invalid '\mk' name {name!r} "
                             "(use letters, digits, '_', '-')")
        if k + 1 >= n or tex[k + 1] != "{":
            raise ValueError(rf"'\mk{{{name}}}' must be followed by '{{content}}'")
        depth, m = 0, k + 1
        while m < n:
            c = tex[m]
            if c == "\\" and m + 1 < n:
                m += 2  # skip escaped character, e.g. '\{'
                continue
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    break
            m += 1
        if depth != 0:
            raise ValueError(rf"unbalanced braces in '\mk{{{name}}}' content")
        inner_raw, inner_marks = extract_marks(tex[k + 2:m])
        start = off
        out.append(inner_raw)
        off += len(inner_raw)
        marks.append({"name": name, "from": start, "to": off})
        for im in inner_marks:      # nested marks: shift into the parent's raw
            marks.append({"name": im["name"],
                          "from": im["from"] + start, "to": im["to"] + start})
        i = m + 1
    return "".join(out), marks


# --------------------------------------------------------------------------
# inline: parse markup into a node list (the AST). The runtime renders each node
# type to DOM (renderInline in runtime.js); lemur.parser emits no inline html. Node
# kinds: text | strong | em | code | math | link | cite | hl | badref.
# --------------------------------------------------------------------------

def _txt(v: str) -> dict:
    return {"type": "text", "value": v}


def cite_nodes(label: str, keys: list, refs: dict) -> list:
    """Turn a reference use ('@ref'/'[label]@ref') into *symbolic* inline nodes.
    The parser only classifies (it has the definitions): a URL ref becomes a
    'link' (its href is the URL — inherent, not resolution); bibliography keys
    collapse into one 'cite' (keys, no numbers); anything internal — or unknown —
    becomes an 'xref' carrying just the target name. Resolving an xref/cite to a
    number, anchor or href is the emitter's job; an unknown target is an
    emitter-time diagnostic, not a distinct node. Label is plain text."""
    out: list = []
    bib_keys: list = []
    for key in keys:
        entry = refs.get(key)
        if entry is not None and entry[2] == "url":
            out.append({"type": "link", "href": entry[1],
                        "content": [_txt(label or entry[1])]})
        elif entry is not None and entry[2] == "bib":
            bib_keys.append(key)
        else:
            node = {"type": "xref", "target": key}
            if label:
                node["content"] = [_txt(label)]
            out.append(node)
    if bib_keys:
        node = {"type": "cite", "keys": bib_keys}
        if label:
            node["prefix"] = [_txt(label)]
        out.append(node)
    return out


def _scan_math_end(text: str, start: int) -> Optional[int]:
    r"""Index of the closing '$' of inline math opened at `start`, mirroring the
    non-greedy '(?:\\.|[^\\$])+?\$' body (at least one content char). None if
    unterminated."""
    m, n = start, len(text)
    while m < n:
        c = text[m]
        if c == "\\" and m + 1 < n:
            m += 2
            continue
        if c == "$":
            return m if m > start else None
        m += 1
    return None


def _scan_braced(text: str, k: int) -> Optional[int]:
    r"""Given text[k] == '{', return the index of the matching '}' (depth-
    counted, escapes skipped), or None if unbalanced."""
    depth, m, n = 0, k, len(text)
    while m < n:
        c = text[m]
        if c == "\\" and m + 1 < n:
            m += 2
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return m
        m += 1
    return None


def _scan_bracket(text: str, start: int) -> Optional[int]:
    r"""Given text[start] == '[', return the index of the matching ']' (nested
    brackets counted, '\[' / '\]' escapes and `code spans` skipped), or None."""
    depth, m, n = 0, start, len(text)
    while m < n:
        c = text[m]
        if c == "\\" and m + 1 < n:
            m += 2
            continue
        if c == "`":                      # a code span is verbatim
            j = text.find("`", m + 1)
            m = j + 1 if j > m else n
            continue
        if c == "[":
            depth += 1
        elif c == "]":
            depth -= 1
            if depth == 0:
                return m
        m += 1
    return None


# a straight quote opens (vs. closes / is an apostrophe) at the start of a run
# or after whitespace, an opening bracket, a dash, or an ellipsis.
_QUOTE_OPEN_AFTER = " \t([{—–…"
# characters a backslash may escape to a literal (markup delimiters + the smart-
# typography chars); '\' before anything else stays a literal backslash.
_ESCAPABLE = set("\\`*_~+[]<>@$'\"-.")


def smart_typography(s: str) -> str:
    r"""Educate the straight ASCII typography of a prose text run: '--' -> en
    dash, '---' -> em dash (longest first), '...' -> ellipsis, and straight
    quotes -> curly. This runs *only* on flushed text runs (parse_inline lifts
    code spans, math and URLs out into their own nodes first), so verbatim
    content is never rewritten — the one rule that keeps code/math safe. Quote
    disambiguation is the usual SmartyPants heuristic: good for prose, imperfect
    for word-initial elision ('twas) and prime marks (5'6\") — code-span those."""
    s = s.replace("---", "—").replace("--", "–").replace("...", "…")
    if "'" not in s and '"' not in s:
        return s
    out = []
    for k, ch in enumerate(s):
        if ch == '"':
            prev = s[k - 1] if k else ""
            out.append("“" if (not prev or prev in _QUOTE_OPEN_AFTER)
                       else "”")
        elif ch == "'":
            prev = s[k - 1] if k else ""
            nxt = s[k + 1] if k + 1 < len(s) else ""
            # a decade ('80s) reads as an apostrophe even in opening position
            opening = (not prev or prev in _QUOTE_OPEN_AFTER) and not nxt.isdigit()
            out.append("‘" if opening else "’")
        else:
            out.append(ch)
    return "".join(out)


def parse_inline(text: str, refs: dict) -> list:
    r"""Parse inline lemur markup into a node list. A left-to-right scan matches
    a backslash escape ('\x' -> literal x) and the verbatim constructs first
    (code spans, math), then '[content]^name' marks, url/mail and reference
    links, then '**'/'__'/'~~'/'++' emphasis, recursing into the content of
    marks/emphasis/links. Straight
    typography on the literal text runs is educated by smart_typography (dashes,
    ellipsis, curly quotes). Malformed constructs fall back to literal text."""
    nodes: list = []
    buf: list = []
    n = len(text)

    def flush() -> None:
        if buf:
            nodes.append(_txt(smart_typography("".join(buf))))
            buf.clear()

    i = 0
    while i < n:
        ch = text[i]
        # '\n' is a hard line break (a '<br>' in flowing output); a literal
        # backslash-n is written '\\n'. Works in any inline run — prose and the
        # cells of a table — wherever the author wants a manual newline.
        if ch == "\\" and i + 1 < n and text[i + 1] == "n":
            flush()
            nodes.append({"type": "break"})
            i += 2
            continue
        # backslash escape: '\' + a special char emits that char literally (so
        # '\"' is a straight quote, '\--' a literal double hyphen, '\@' a literal
        # at-sign, '\*' literal asterisks). A '\' before an ordinary char stays a
        # literal backslash (CommonMark-style). The smart-typography chars must
        # bypass smart_typography, so they are flushed out as their own text
        # node; markup delimiters can just sit literally in the buffer.
        if ch == "\\" and i + 1 < n and text[i + 1] in _ESCAPABLE:
            esc = text[i + 1]
            if esc in "'\"-.":
                flush()
                nodes.append(_txt(esc))
            else:
                buf.append(esc)
            i += 2
            continue
        # code span `...`
        if ch == "`":
            j = text.find("`", i + 1)
            if j > i:
                flush()
                nodes.append({"type": "code", "value": text[i + 1:j]})
                i = j + 1
                continue
        # inline math $...$
        elif ch == "$":
            end = _scan_math_end(text, i + 1)
            if end is not None:
                flush()
                tex, marks = extract_marks(text[i + 1:end])
                node = {"type": "math", "tex": tex}
                if marks:
                    node["marks"] = marks
                nodes.append(node)
                i = end + 1
                continue
        # <url> or <mail@domain>
        elif ch == "<":
            gt = text.find(">", i + 1)
            if gt > i:
                inner = text[i + 1:gt]
                if re.fullmatch(r"https?://\S+", inner):
                    flush()
                    nodes.append({"type": "link", "href": inner,
                                  "content": [_txt(inner)]})
                    i = gt + 1
                    continue
                if re.fullmatch(r"[\w.+-]+@[\w.-]+\.\w+", inner):
                    flush()
                    nodes.append({"type": "link", "href": "mailto:" + inner,
                                  "content": [_txt(inner)]})
                    i = gt + 1
                    continue
        # [content]{style}^name<spec> — a styled/named/revealed span (each part
        # optional), or [label]@(target) / [label]@ref (a reference)
        elif ch == "[":
            rb = _scan_bracket(text, i)
            if rb is not None:
                inner, rest = text[i + 1:rb], text[rb + 1:]
                sm = RE_SPAN_SUFFIX.match(rest)
                style_s, name, spec = sm.group(1), sm.group(2), sm.group(3)
                style = parse_style(style_s) if style_s else {}
                if name or spec or style:
                    flush()
                    node = ({"type": "mark", "name": name} if name
                            else {"type": "span"})
                    node["content"] = parse_inline(inner, refs)
                    if style:
                        node["style"] = style
                    if spec:
                        node["reveal"] = {"spec": spec}
                    nodes.append(node)
                    i = rb + 1 + sm.end()
                    continue
                sub, adv = _parse_ref_use(inner, rest, refs)
                if sub is not None:
                    flush()
                    nodes.extend(sub)
                    i = rb + 1 + adv
                    continue
        # '@ref' / '@(a, b)'. An '@' inside an email address (local@domain.tld)
        # stays literal; otherwise it is a reference — even abutting a word, so
        # 'Kording@jonas2010' is a citation, not mistaken for an email.
        elif ch == "@" and not (
                buf and (buf[-1].isalnum() or buf[-1] in "._+-")
                and re.match(r"@[\w.-]+\.\w{2,}", text[i:])):
            sub, adv = _parse_ref_use("", text[i:], refs)
            if sub is not None:
                flush()
                nodes.extend(sub)
                i = i + adv
                continue
        # emphasis (** before __)
        elif text.startswith("**", i):
            close = text.find("**", i + 2)
            if close > i + 1:
                flush()
                nodes.append({"type": "strong",
                              "content": parse_inline(text[i + 2:close], refs)})
                i = close + 2
                continue
        elif text.startswith("__", i):
            close = text.find("__", i + 2)
            if close > i + 1:
                flush()
                nodes.append({"type": "emph",
                              "content": parse_inline(text[i + 2:close], refs)})
                i = close + 2
                continue
        elif text.startswith("~~", i):
            close = text.find("~~", i + 2)
            if close > i + 1:
                flush()
                nodes.append({"type": "strike",
                              "content": parse_inline(text[i + 2:close], refs)})
                i = close + 2
                continue
        elif text.startswith("++", i):
            close = text.find("++", i + 2)
            if close > i + 1:
                flush()
                nodes.append({"type": "underline",
                              "content": parse_inline(text[i + 2:close], refs)})
                i = close + 2
                continue
        buf.append(ch)
        i += 1
    flush()
    return nodes


def _parse_ref_use(label: str, rest: str, refs: dict):
    """Parse a reference use following an optional '[label]': '@(targets)' or
    '@ref'. Returns (nodes, consumed_len_of_rest) or (None, 0) if `rest` does
    not begin a reference use."""
    if rest.startswith("@("):
        end = rest.find(")")
        if end < 0:
            return None, 0
        target = rest[2:end].strip()
        if re.match(r"^https?://", target):
            return [{"type": "link", "href": target,
                     "content": [_txt(label)]}], end + 1
        keys = [k.strip() for k in target.split(",")]
        return cite_nodes(label, keys, refs), end + 1
    m = re.match(r"@([\w-]+)", rest)
    if m:
        return cite_nodes(label, [m.group(1)], refs), m.end()
    return None, 0


# --------------------------------------------------------------------------
# structured leaf-block AST builders. Every block becomes typed node data with
# inline-node content; the runtime (runtime.js) turns each node type into DOM.
# lemur.parser emits no block html, no geometry, no DOM ids: the AST is the neutral
# document (spec/ast.schema.json). Annotation geometry now lives only in the
# emitter (runtime.js), computed from the marks at layout time.
# --------------------------------------------------------------------------


def reveal_of(step: int, when: Optional[str]) -> Optional[dict]:
    """Neutral reveal spec from the internal (step, when) fields: an explicit
    overlay spec wins; otherwise a positive step n means 'from n onward' (n-).
    Integer step *numbers* never leak into the AST — the emitter assigns them."""
    if when:
        return {"spec": when}
    if step and step > 0:
        return {"spec": f"{step}-"}
    return None


def build_list(items: list, refs: dict) -> dict:
    """Turn the flat, whitespace-tagged list items into a nested 'list' node. An
    item nests under the previous one when its indentation extends it; equal
    indentation is a sibling; a shallower indent closes levels. Each nesting
    level is its own list node with its own 'ordered' flag."""
    root = {"type": "list", "ordered": bool(items and items[0][2]), "items": []}
    stack: list = []   # each: {"ws": ws, "node": list_node, "last": item}

    def item_node(text, step, when):
        node = {"content": parse_inline(text, refs)}
        rev = reveal_of(step, when)
        if rev:
            node["reveal"] = rev
        return node

    for ws, text, ordered, step, when in items:
        node = item_node(text, step, when)
        if not stack:
            root["items"].append(node)
            stack.append({"ws": ws, "node": root, "last": node})
        elif ws == stack[-1]["ws"]:
            stack[-1]["node"]["items"].append(node)
            stack[-1]["last"] = node
        elif ws.startswith(stack[-1]["ws"]) and len(ws) > len(stack[-1]["ws"]):
            sub = {"type": "list", "ordered": bool(ordered), "items": [node]}
            stack[-1]["last"]["sublist"] = sub
            stack.append({"ws": ws, "node": sub, "last": node})
        else:
            while len(stack) > 1 and ws != stack[-1]["ws"]:
                stack.pop()
            stack[-1]["node"]["items"].append(node)
            stack[-1]["last"] = node
    return root


def code_ast(d: dict) -> dict:
    """Code payload: language and raw source. Highlight groups carry a reveal
    spec ('from step n onward') plus the 1-based lines they emphasise; when two
    groups are active the emitter takes the last. Splitting source into line
    spans is the emitter's choice."""
    node: dict = {"source": d["text"]}
    if d.get("lang"):
        node["language"] = d["lang"]
    highlights = d.get("highlights") or {}
    if highlights:
        node["highlights"] = [
            {"reveal": {"spec": f"{int(step)}-"},
             "lines": [int(n) for n in lines]}
            for step, lines in sorted(highlights.items(),
                                      key=lambda kv: int(kv[0]))]
    return node


TABLE_ALIGN = {"l": "left", "r": "right", "c": "center"}


def table_ast(d: dict, refs: dict) -> dict:
    columns = [{"heading": parse_inline(c["name"], refs),
                "align": TABLE_ALIGN.get(c["align"], "left")}
               for c in d["cols"]]
    rows: list = []
    for row in d["rows"]:
        if row == "sep-strong":
            rows.append({"separator": "strong"})
        elif row == "sep-light":
            rows.append({"separator": "light"})
        else:
            rows.append({"cells": [parse_inline(cell, refs) for cell in row]})
    node: dict = {"columns": columns, "rows": rows}
    if not d.get("header", True):
        node["header"] = False
    if d["title"]:
        node["title"] = parse_inline(d["title"], refs)
    if d["caption"]:
        node["caption"] = parse_inline(d["caption"], refs)
    return node


def figure_ast(d: dict, refs: dict) -> dict:
    """Figure payload: sources, optional overlay layers (a reveal spec per
    source beyond the first), author-intent width/height (fraction/length, not
    pixels), and caption. No 'sized' flag or geometry — the emitter derives it."""
    node: dict = {"sources": d["srcs"]}
    layer_steps = d.get("layer_steps") or []
    if layer_steps:
        node["layers"] = [{"spec": f"{int(s)}-"} for s in layer_steps]
    if d["width"]:
        node["width"] = d["width"]
    if d["height"]:
        node["height"] = d["height"]
    if d["caption"]:
        node["caption"] = parse_inline(d["caption"], refs)
    return node


def anim_ast(d: dict) -> dict:
    """Animation intent: the source module and its viewport (where on the slide it
    renders). No geometry, no step count — the emitter runs the module to get the
    IR (nodes/tracks/beats/camera) and bakes it into the viewport."""
    node: dict = {"src": d["src"], "viewport": d.get("viewport") or "body"}
    if d.get("width"):
        node["width"] = d["width"]
    if d.get("height"):
        node["height"] = d["height"]
    return node


def shader_ast(d: dict) -> dict:
    """Live-shader intent: the GLSL source, where it renders, how many steps it
    drives, and an optional soundtrack preset / resolution scale."""
    node: dict = {"src": d["src"], "viewport": d.get("viewport") or "body"}
    for k in ("width", "height", "sound", "quality"):
        if d.get(k):
            node[k] = d[k]
    if d.get("steps"):
        node["steps"] = int(d["steps"])
    return node


def plot_ast(d: dict, refs: dict) -> dict:
    """Figure intent: the matplotlib source module + author-intent size/caption.
    The emitter runs the module and bakes the figure to a self-contained SVG."""
    node: dict = {"src": d["src"]}
    if d.get("width"):
        node["width"] = d["width"]
    if d.get("height"):
        node["height"] = d["height"]
    if d.get("caption"):
        node["caption"] = parse_inline(d["caption"], refs)
    return node


def annotate_ast(items: list, refs: dict) -> dict:
    """Annotation intent: one item per named mark with its colour (palette
    default), emphasis, optional label, and reveal. No geometry — how it is
    drawn (callouts+arrows, margin notes, or nothing) is the emitter's choice."""
    palette = ["#c05d28", "#7a4b94", "#3a7d44", "#2e5e6e"]
    out = []
    for i, it in enumerate(items):
        color, styles = it["color"], it.get("styles") or []
        if not color and not styles:
            color = palette[i % len(palette)]
        node: dict = {"mark": it["name"]}
        if it["text"]:
            node["label"] = parse_inline(it["text"], refs)
        if color:
            node["color"] = color
        if styles:
            node["emphasis"] = styles
        rev = reveal_of(it["step"], None)
        if rev:
            node["reveal"] = rev
        out.append(node)
    return {"items": out}


def connect_ast(links: list) -> dict:
    """Connector intent: directed links between two named marks, revealed
    progressively. Neutral 'connect mark A to mark B' — no geometry; drawing
    (an arrow, a plain line, or nothing) is the emitter's choice. Slide-only
    (a LaTeX emitter drops these; a TikZ one may render them later)."""
    out = []
    for lk in links:
        node: dict = {"from": lk["from"], "to": lk["to"], "dir": lk["dir"]}
        if lk.get("color"):
            node["color"] = lk["color"]
        if lk.get("styles"):
            node["styles"] = lk["styles"]
        rev = reveal_of(lk["step"], None)
        if rev:
            node["reveal"] = rev
        out.append(node)
    return {"links": out}


def bibliography_ast(entries: list, refs: dict) -> dict:
    return {"entries": [{"key": e["key"],
                         "content": parse_inline(e["text"], refs)}
                        for e in entries]}


def notes_ast(text: str, refs: dict) -> dict:
    return {"body": [{"type": "para", "content": parse_inline(p.strip(), refs)}
                     for p in re.split(r"\n\s*\n", text) if p.strip()]}


def parse_transition(meta: dict) -> tuple[str, str]:
    """'!transition <slide> [<step>]': the first word is the across-slide
    transition (default none), the second the within-slide step transition for
    appearing elements (default fade). Slide: none|fade|slide|push ('slide' moves
    the whole slide, 'push' only the content so the header/footer stay put); step:
    none|fade|rise. Unknown words warn and fall back."""
    tparts = meta.get("transition", "none").split()
    slide_trans = tparts[0] if tparts else "none"
    step_trans = tparts[1] if len(tparts) > 1 else "fade"
    if slide_trans not in ("none", "fade", "slide", "push"):
        print(f"lemur: warning: unknown slide transition '{slide_trans}' "
              "(use 'none', 'fade', 'slide' or 'push'); using 'none'",
              file=sys.stderr)
        slide_trans = "none"
    if step_trans not in ("none", "fade", "rise"):
        print(f"lemur: warning: unknown step transition '{step_trans}' "
              "(use 'none', 'fade' or 'rise'); using 'fade'", file=sys.stderr)
        step_trans = "fade"
    return slide_trans, step_trans


def iter_blocks(blocks: list):
    """Yield every block, descending into '!columns'/'!stack'/environment
    children."""
    for b in blocks:
        yield b
        if b.kind == "columns":
            for col in b.data["columns"]:
                yield from iter_blocks(col["blocks"])
        elif b.kind == "stack":
            for lyr in b.data["layers"]:
                yield from iter_blocks(lyr["blocks"])
        elif b.kind in ("env", "style"):
            yield from iter_blocks(b.data["blocks"])


# --------------------------------------------------------------------------
# AST emission: parse -> AST (fully-typed nodes) -> JSON, embedded in a thin
# shell and rendered to DOM at runtime by runtime.js. The AST is the single
# source of truth; lemur.parser emits no html at all. Every block and every inline
# run is a typed node with structured fields, and the runtime has a distinct
# render path per node type — so a new node type or a restyle of one is a change
# in the runtime, never here.
# --------------------------------------------------------------------------

# internal block kind -> neutral AST node type (most are 1:1)
BLOCK_TYPE = {"image": "figure", "bib": "bibliography"}
# node types that may carry a reveal spec (per the schema)
REVEAL_OK = {"heading", "para", "list", "code", "math", "table", "image",
             "columns", "env", "style"}
# node types that may carry a cross-reference id (per the schema)
ID_OK = {"heading", "math", "code", "table", "image", "env", "style"}


def block_to_ast(b: Block, refs: dict) -> dict:
    """One neutral block node. Carries reveal *intent* (never integer steps) and
    a symbolic cross-reference `id` where the schema allows; no DOM ids, no
    geometry."""
    node: dict = {"type": BLOCK_TYPE.get(b.kind, b.kind)}
    if b.kind == "columns":
        if b.data.get("style"):
            node["style"] = b.data["style"]
        node["columns"] = []
        for i, col in enumerate(b.data["columns"]):
            widths = b.data["widths"]
            c: dict = {"weight": widths[i] if i < len(widths) else 1,
                       "body": [block_to_ast(cb, refs)
                                for cb in col["blocks"]]}
            if col.get("style"):
                c["style"] = col["style"]
            node["columns"].append(c)
    elif b.kind == "stack":
        node["layers"] = [
            {"reveal": {"spec": lyr["when"]},
             "body": [block_to_ast(cb, refs) for cb in lyr["blocks"]]}
            for lyr in b.data["layers"]]
    elif b.kind == "env":
        node["kind"] = b.data["kind"]
        if b.data.get("title"):
            node["title"] = parse_inline(b.data["title"], refs)
        node["body"] = [block_to_ast(cb, refs) for cb in b.data["blocks"]]
    elif b.kind == "style":
        if b.data.get("style"):
            node["style"] = b.data["style"]
        node["body"] = [block_to_ast(cb, refs) for cb in b.data["blocks"]]
    elif b.kind == "para":
        node["content"] = parse_inline(b.data["text"], refs)
    elif b.kind == "heading":
        node["level"] = b.data["level"]
        node["content"] = parse_inline(b.data["text"], refs)
    elif b.kind == "math":
        node["tex"] = b.data["tex"]
        if b.data.get("marks"):
            node["marks"] = b.data["marks"]
    elif b.kind == "list":
        node = build_list(b.data["items"], refs)
    elif b.kind == "code":
        node.update(code_ast(b.data))
    elif b.kind == "table":
        node.update(table_ast(b.data, refs))
    elif b.kind == "image":
        node.update(figure_ast(b.data, refs))
    elif b.kind == "anim":
        node.update(anim_ast(b.data))
    elif b.kind == "shader":
        node.update(shader_ast(b.data))
    elif b.kind == "plot":
        node.update(plot_ast(b.data, refs))
    elif b.kind == "annotate":
        node.update(annotate_ast(b.data["items"], refs))
    elif b.kind == "connect":
        node.update(connect_ast(b.data["links"]))
    elif b.kind == "spacer":
        if b.data.get("size"):
            node["size"] = b.data["size"]
    elif b.kind == "bib":
        node.update(bibliography_ast(b.data["entries"], refs))
    elif b.kind == "notes":
        node.update(notes_ast(b.data["text"], refs))
    else:
        raise LemurError(f"internal error: unknown block kind '{b.kind}'")
    rid = b.data.get("ref") if isinstance(b.data, dict) else None
    if rid and b.kind in ID_OK:
        node["id"] = rid
    if b.kind in REVEAL_OK:
        rev = reveal_of(b.step, b.when)
        if rev:
            node["reveal"] = rev
    return node


def slide_to_body(slide: Slide, refs: dict) -> list:
    """A slide contributes a 'pagebreak' marker (its title/role/label/variant)
    followed by its blocks to the flat document body. Slides are a pagination
    view: a paginating emitter starts a page here, a flowing one ignores it."""
    pb: dict = {"type": "pagebreak"}
    if slide.title:
        pb["title"] = parse_inline(slide.title, refs)
    if slide.kind != "content":
        pb["role"] = slide.kind
    if slide.ref:
        pb["id"] = slide.ref
    if slide.styles:
        pb["variant"] = [s.lstrip(".") for s in slide.styles]
    return [pb] + [block_to_ast(b, refs) for b in slide.blocks]


def meta_ast(meta: dict) -> dict:
    """Neutral document metadata."""
    out: dict = {}
    for key in ("title", "subtitle", "date"):
        if meta.get(key):
            out[key] = meta[key]
    if meta.get("author"):
        out["authors"] = [meta["author"]]
    if meta.get("institute"):
        out["affiliation"] = meta["institute"]
    return out


def presentation_ast(meta: dict, refs: dict) -> dict:
    """Optional presentation hints (theme/aspect/transition/chrome). Only what
    the author expressed; an emitter supplies its own defaults for the rest."""
    out: dict = {}
    if meta.get("theme"):
        out["theme"] = meta["theme"]
    if meta.get("aspect"):
        out["aspect"] = meta["aspect"]
    if meta.get("transition"):
        across, step = parse_transition(meta)
        out["transition"] = {"across": across, "step": step}
    if meta.get("header"):
        out["header"] = parse_inline(meta["header"], refs)
    if meta.get("footer"):
        out["footer"] = parse_inline(meta["footer"], refs)
    if meta.get("logo"):
        out["logo"] = meta["logo"]
    if "slidenumbers" in meta:
        out["slideNumbers"] = meta["slidenumbers"].lower() != "off"
    if meta.get("titleimage"):
        out["titleImage"] = meta["titleimage"]
    # progress bar: '!progress [top|bottom]' -> a hint; '!progress off' / absent
    # leaves it off. A bare '!progress' means on with the default placement.
    prog = meta.get("progress")
    if prog is not None and prog.strip().lower() != "off":
        pos = prog.strip().lower()
        out["progress"] = {"position": pos} if pos in ("top", "bottom") else True
    return out


def deck_to_ast(deck: Deck) -> dict:
    """Serialize the parsed deck to the neutral document AST (spec/ast.schema.
    json): metadata + optional presentation hints + a flat body of blocks, with
    `pagebreak` markers where `!slide`/`!section` chunked the source. No cover is
    synthesized and no slide is numbered here — those are emitter decisions."""
    refs = deck.refs
    body: list = []
    for group in deck.groups:
        for slide in group:
            body.extend(slide_to_body(slide, refs))
    doc: dict = {"astVersion": lmrast.AST_VERSION,
                 "meta": meta_ast(deck.meta), "body": body}
    pres = presentation_ast(deck.meta, refs)
    if pres:
        doc["presentation"] = pres
    return doc


# --------------------------------------------------------------------------
# cli
# --------------------------------------------------------------------------


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="parse a lemur (.lmr) document to its neutral AST (JSON, "
                    "spec/ast.schema.json) \u2014 the interface the emitters "
                    "(lmr2slides, lmr2tex) consume")
    ap.add_argument("input", help="the .lmr document to parse")
    ap.add_argument("--ast", action="store_true",
                    help="emit the AST as JSON to stdout (this is the only "
                    "output; the flag is accepted for explicitness)")
    args = ap.parse_args(argv)
    try:
        deck = Parser(load_lines(args.input)).parse()
    except LemurError as exc:
        print(f"lemur: error: {exc}", file=sys.stderr)
        return 1
    print(lmrast.dumps(deck_to_ast(deck)))
    return 0



if __name__ == "__main__":
    sys.exit(main())
