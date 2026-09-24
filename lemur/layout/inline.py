"""Inline run layout: a list of inline AST nodes -> wrapped, positioned pieces.

One engine, modelled on CSS inline formatting so a slide wraps and spaces the
way the HTML deck did:

* **Items.** Text runs are shaped per run (Pango) and split into word boxes and
  space glue by advance width; inline maths is one box per fragment (LaTeX).
  Adjacent boxes with no glue between them (``**bold**,``) form one unbreakable
  word, so a line never breaks between a word and its punctuation.
* **Line boxes.** Every inline box contributes its CSS extent above/below the
  baseline: text gets its font's ascent/descent plus *half-leading* for the
  block's ``line-height`` (a unitless factor of the font size, like CSS), maths
  its ink height/depth (a replaced box, like MathJax's SVG). A line box is the
  union with the block's own strut, so a tall fraction grows its line and plain
  text lines are exactly ``line_height`` apart.
* **Alignment** is per line (``left``/``center``/``right``) within the wrap width.
* **Reveals.** A ``span``/``mark`` with an overlay spec (``[text]<2->``) gates
  its pieces; hidden runs keep their space, so a reveal never reflows the line.

Pieces are ``(subpaths, closed, fill, mark, gate)`` in em units of the block
font, y-up, with the first baseline at ``y = 0``; ``gate`` is ``None`` (always)
or a step gate (:mod:`lemur.layout.steps`).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from ..typeset import latex, pango
from ..typeset.geometry import bbox_of
from . import diag, steps

__all__ = ["TextStyle", "Laid", "layout_block", "layout_inline", "LINE_HEIGHT",
           "math_scale_for"]

CODE_COLOR = "#e0b070"
LINK_COLOR = "#6cb6ff"

#: CSS ``line-height`` of running text (``p``/``li``) in the HTML deck.
LINE_HEIGHT = 1.45

#: The maths font's x-height MathJax matches the text's ``ex`` against (its
#: TeX-font parameter): maths is scaled by ``text x-height / 0.442``. LaTeX's
#: Latin Modern is the same design, so the same factor makes the baked maths
#: exactly as large as the HTML deck's.
_MATH_XHEIGHT = 0.442
_LM_XHEIGHT = 0.4306

#: CSS ``sup``: ``font-size: smaller`` and ``vertical-align: super``.
_SUP_SIZE = 1 / 1.2
_SUP_RISE = 0.36


@dataclass
class TextStyle:
    font: str          # serif/body family
    mono: str          # monospace family
    color: str         # default fill
    weight: "str | int" = "normal"
    italic: bool = False
    is_mono: bool = False
    code_color: str = CODE_COLOR   # inline `code`
    link_color: str = LINK_COLOR   # links / cross-references / citations
    code_panel: str = "#eef1f4"    # inline `code` chip background
    strike: bool = False           # strikethrough decoration
    underline: bool = False        # underline decoration
    bg: "str | None" = None        # a run background (inline-code chip, span bg)
    size: float = 1.0              # font size relative to the block's em
    rise: float = 0.0              # baseline shift (block em, up) — superscripts
    accent: str = LINK_COLOR       # the theme accent (`.accent` spans)
    pad: float = 0.0               # inline horizontal padding (em of this run)
    bad_ink: str = "#b00020"       # an unresolved reference/citation
    bad_bg: str = "#ffeaea"
    letter_spacing: float = 0.0    # CSS letter-spacing (em of this run), after every character

    def derive(self, **kw) -> "TextStyle":
        return TextStyle(**{**self.__dict__, **kw})

    @property
    def family(self) -> str:
        return self.mono if self.is_mono else self.font


@dataclass
class Laid:
    """A laid-out inline block: pieces plus the CSS box metrics (all em)."""
    pieces: list
    height: float = 0.0            # total height of the stacked line boxes
    top: float = 0.0               # from the first line box's top to its baseline
    width: float = 0.0             # the widest line (natural width when unwrapped)
    baselines: list = field(default_factory=list)  # each line's baseline, down from the first

    @property
    def lines(self) -> int:
        return len(self.baselines)


_xheight_cache: dict = {}


def math_scale_for(font: str) -> float:
    """Scale LaTeX maths so its x-height matches the text font's, as MathJax did
    (``matchFontHeight``). Clamped to a sane range."""
    if font not in _xheight_cache:
        xh = pango.x_height(font)
        if not xh:                                   # no OS/2 metric: the ink of an "x"
            try:
                s = pango.shape("x", font=font)
                _, _, _, maxy = bbox_of([sp for cl in s.clusters for sp in cl.subpaths])
                xh = maxy * 0.965 if maxy > 0.2 else _MATH_XHEIGHT   # minus the overshoot
            except Exception:  # pragma: no cover - Pango missing is reported elsewhere
                xh = _MATH_XHEIGHT
        _xheight_cache[font] = max(0.85, min(1.25, xh / _MATH_XHEIGHT))
    return _xheight_cache[font]


def _span_style(style: "TextStyle", sd) -> "TextStyle":
    """Fold a span/style `{color, classes, bg}` dict into a derived TextStyle."""
    if not sd:
        return style
    kw: dict = {}
    classes = sd.get("classes") or []
    if "accent" in classes:
        kw["color"] = style.accent
    if sd.get("color"):
        kw["color"] = sd["color"]
    if sd.get("bg"):
        kw["bg"] = sd["bg"]
        kw["pad"] = 0.0
    if "bold" in classes:
        kw["weight"] = "bold"
    if any(c in classes for c in ("emph", "italic", "it")):
        kw["italic"] = True
    if "underline" in classes:
        kw["underline"] = True
    if "strike" in classes:
        kw["strike"] = True
    return style.derive(**kw) if kw else style


# --------------------------------------------------------------------------
# items: boxes, glue, breaks
# --------------------------------------------------------------------------


@dataclass
class _Box:
    pieces: list    # (subpaths, closed, color, mark, gate), origin x=0, baseline y=0
    width: float    # advance width in em
    asc: float      # extent above the baseline (em), incl. half-leading
    desc: float     # extent below the baseline (em), incl. half-leading


@dataclass
class _Glue:
    width: float
    math: bool = False      # a break point inside a formula (never merged with a text space)


class _Break:
    pass


@dataclass
class _Env:
    line_height: float
    math_scale: float


_metric_cache: dict = {}


def _metrics(style: TextStyle) -> tuple:
    key = (style.family, str(style.weight), style.italic)
    if key not in _metric_cache:
        _metric_cache[key] = pango.font_metrics(style.family, style.weight, style.italic)
    return _metric_cache[key]


def _extent(style: TextStyle, lh: float) -> tuple:
    """CSS extent of an inline text box: (above, below) the parent baseline."""
    a, d = _metrics(style)
    s = style.size
    half = (lh * s - (a + d) * s) / 2.0
    return a * s + half + style.rise, d * s + half - style.rise


def _rect_sub(x0: float, x1: float, y0: float, y1: float, r: float = 0.0):
    """A closed (optionally rounded) rectangle as one cubic subpath."""
    if r <= 0 or r * 2 > min(x1 - x0, y1 - y0):
        corners = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
        pts = []
        for i in range(4):
            a = np.array(corners[i], float)
            b = np.array(corners[(i + 1) % 4], float)
            pts += [a, a + (b - a) / 3, a + 2 * (b - a) / 3]
        pts.append(np.array(corners[0], float))
        return np.array(pts)
    k = 0.5523 * r

    def line(a, b):
        a, b = np.array(a, float), np.array(b, float)
        return [a + (b - a) / 3, a + 2 * (b - a) / 3, b]

    p = [np.array((x0 + r, y0), float)]
    p += line((x0 + r, y0), (x1 - r, y0))
    p += [np.array((x1 - r + k, y0)), np.array((x1, y0 + r - k)), np.array((x1, y0 + r))]
    p += line((x1, y0 + r), (x1, y1 - r))
    p += [np.array((x1, y1 - r + k)), np.array((x1 - r + k, y1)), np.array((x1 - r, y1))]
    p += line((x1 - r, y1), (x0 + r, y1))
    p += [np.array((x0 + r - k, y1)), np.array((x0, y1 - r + k)), np.array((x0, y1 - r))]
    p += line((x0, y1 - r), (x0, y0 + r))
    p += [np.array((x0, y0 + r - k)), np.array((x0 + r - k, y0)), np.array((x0 + r, y0))]
    return np.array(p)


def _is_space(t: str) -> bool:
    return t == "" or (t.isspace() and "\u00a0" not in t and "\u202f" not in t)


#: CSS ``white-space: normal``: a run of spaces/tabs/newlines is one space
#: (no-break spaces are content, not whitespace).
_WS = None


def _collapse_ws(text: str) -> str:
    import re

    global _WS
    if _WS is None:
        _WS = re.compile(r"[ \t\n\r\f\v]+")
    return _WS.sub(" ", text)


_HYPHENS = ("-", "\u2010")          # break after, unless a digit follows (UAX #14 HY × NU)
_DASHES_AFTER = ("\u2013",)         # en dash (BA): break after
_DASHES_BOTH = ("\u2014",)          # em dash (B2): break before and after


def _break_after(cur: str, nxt: str) -> bool:
    if not nxt or _is_space(nxt):
        return False
    if cur in _HYPHENS:
        return not nxt[:1].isdigit()
    return cur in _DASHES_AFTER or cur in _DASHES_BOTH


def _words_from_run(text: str, style: TextStyle, env: _Env, mark=None, gate=None) -> list:
    """Shape a same-style text run and split it into word boxes + space glue,
    using advance widths (so positions stay consistent with inline maths). A run
    may carry a background chip (inline `code`, span bg) and strike/underline."""
    if not text:
        return []
    shaped = pango.shape(text, font=style.family, weight=style.weight, italic=style.italic)
    s, rise = style.size, style.rise
    asc, desc = _extent(style, env.line_height)
    a_font, d_font = _metrics(style)
    lift = np.array([0.0, rise])

    words: list = []   # [glyph pieces, width, trailing glue width]
    items: list = []   # ("w", idx) | ("g", width)
    wp: list = []
    ww = 0.0
    pen0 = None
    pen = 0.0

    def flush():
        nonlocal wp, ww, pen0
        if wp:
            off = np.array([pen0, 0.0])
            words.append([[([(sp - off) * s + lift for sp in sps], cls) for sps, cls in wp], ww * s, 0.0])
            items.append(("w", len(words) - 1))
        wp, ww, pen0 = [], 0.0, None

    ls = style.letter_spacing
    extra = 0.0                     # accumulated letter-spacing before this cluster
    clusters = shaped.clusters
    for ci, cl in enumerate(clusters):
        adv = cl.x_advance + ls
        if cl.text in _DASHES_BOTH and wp:               # a break opportunity before an em dash
            flush()
            items.append(("g", 0.0))
        if _is_space(cl.text):
            flush()
            if adv > 0:
                items.append(("g", adv * s))
                if words and items[-2:-1] and items[-2][0] == "w":
                    words[-1][2] = adv * s
        else:
            if pen0 is None:
                pen0 = pen
            if cl.subpaths:
                if extra:
                    shift = np.array([extra, 0.0])
                    wp.append(([sp + shift for sp in cl.subpaths], cl.closed))
                else:
                    wp.append((cl.subpaths, cl.closed))
            ww += adv
            if _break_after(cl.text, clusters[ci + 1].text if ci + 1 < len(clusters) else ""):
                pen += adv
                extra += ls
                flush()
                items.append(("g", 0.0))                  # a zero-width break opportunity
                continue
        pen += adv
        extra += ls
    flush()
    if not words:
        return [_Glue(w) for k, w in items if k == "g"]

    pad = style.pad * s
    out: list = []
    last = len(words) - 1
    for k, v in items:
        if k == "g":
            out.append(_Glue(v))
            continue
        i = v
        glyphs, w, trail = words[i]
        lead = pad if i == 0 else 0.0
        tail = pad if i == last else 0.0
        width = lead + w + tail
        pieces: list = []
        if style.bg:
            # the chip spans the run continuously: a word's chip also covers the
            # space after it when another word of the same run follows
            x1 = width + (trail if i < last else 0.0)
            r = 0.08 * s if style.pad else 0.0
            pieces.append(([_rect_sub(0.0, x1, -d_font * s + rise, a_font * s + rise, r)], [True],
                           style.bg, mark, gate))
        for sps, cls in glyphs:
            pieces.append(([sp + np.array([lead, 0.0]) for sp in sps], cls, style.color, mark, gate))
        span_w = w + (trail if i < last else 0.0)
        if style.strike:
            pieces.append(([_rect_sub(lead, lead + span_w, 0.26 * s + rise, 0.31 * s + rise)], [True],
                           style.color, mark, gate))
        if style.underline:
            pieces.append(([_rect_sub(lead, lead + span_w, -0.11 * s + rise, -0.06 * s + rise)], [True],
                           style.color, mark, gate))
        out.append(_Box(pieces, width, asc, desc))
    return out


def _math_box(node: dict, style: TextStyle, env: _Env, mark=None, gate=None) -> "_Box | None":
    tex = node.get("tex", "")
    if not tex.strip():
        return None
    try:
        glyphs, box = latex.tex_render_marked(tex, node.get("marks") or [], "inline")
    except latex.LatexError as exc:
        diag.warn(f"LaTeX error in ${tex}$ — shown as source. {_first_error(exc)}")
        return None
    all_sp = [sp for g in glyphs for sp in g.subpaths]
    if not all_sp and box is None:
        return None
    sc = style.size * env.math_scale
    if box is not None:
        # TeX's box (like MathJax's): its advance keeps the side bearings, `\,`,
        # `\quad` and operator spacing; height/depth feed the line box
        minx, width, height, depth = 0.0, box.width, box.height, box.depth
    else:                                            # fall back to the ink
        minx, miny, maxx, maxy = bbox_of(all_sp)
        width, height, depth = maxx - minx, maxy, -miny
    off = np.array([minx, 0.0])
    lift = np.array([0.0, style.rise])
    pieces = []
    for g in glyphs:
        col = g.fill if (g.fill and g.fill not in ("none", "currentColor")) else style.color
        pieces.append(([(sp - off) * sc + lift for sp in g.subpaths], g.closed, col,
                       g.meta.get("mark") or mark, gate))
    return _Box(pieces, max(width, 0.0) * sc, max(height, 0.0) * sc + style.rise,
                max(depth, 0.0) * sc - style.rise)


def _first_error(exc) -> str:
    """The first ``! …`` line of a LaTeX failure message."""
    for ln in str(exc).splitlines():
        if ln.startswith("!"):
            return ln
    return str(exc).splitlines()[0] if str(exc) else ""


#: TeX relations MathJax 4 may break an inline formula *before* (top level only).
_REL_CMDS = frozenset((
    "le leq ge geq ne neq in notin ni subset subseteq supset supseteq approx sim simeq "
    "equiv cong propto to rightarrow leftarrow Rightarrow Leftarrow leftrightarrow "
    "Leftrightarrow longrightarrow Longrightarrow longleftarrow iff implies impliedby "
    "mapsto mid parallel coloneqq eqqcolon ll gg models vdash dashv prec succ preceq "
    "succeq sqsubseteq sqsupseteq asymp doteq triangleq perp").split())
_REL_CHARS = "=<>≤≥≠∈∉∋⊂⊆⊃⊇≈∼≃≡≅∝→←↔⇒⇐⇔↦∣∥≔≪≫⊨⊢"
#: explicit spaces MathJax also breaks at (the space stays at the line end)
_SPACE_CMDS = frozenset((",", ";", ":", "quad", "qquad", " "))


def _ends_in_space(tex: str) -> bool:
    import re

    return bool(re.search(r"\\(,|;|:|quad|qquad| )\s*$", tex))


def _split_relations(tex: str) -> list:
    """Split inline TeX before each top-level relation (not the first atom), so a
    long formula can wrap there like MathJax's in-line breaking. Returns the
    pieces (``[tex]`` when there is nothing to split)."""
    if any(t in tex for t in ("&", "\\\\", "\\begin", "\\mk", "\\color")):
        return [tex]
    pieces, cur = [], []
    depth = 0          # {} groups and \left…\right
    i, n = 0, len(tex)
    script = False     # the next token is a sub/superscript argument
    prev_rel = False   # the last top-level atom was a relation (`<=`: no break inside)
    while i < n:
        c = tex[i]
        if c == "\\":
            j = i + 1
            while j < n and tex[j].isalpha():
                j += 1
            name = tex[i + 1:j] if j > i + 1 else tex[i + 1:i + 2]
            j = max(j, i + 2)
            if name == "left":
                depth += 1
            elif name == "right":
                depth = max(0, depth - 1)
            is_rel = depth == 0 and not script and name in _REL_CMDS
            if is_rel and not prev_rel and "".join(cur).strip():
                pieces.append("".join(cur))
                cur = []
            cur.append(tex[i:j])
            if depth == 0 and not script and name not in ("left", "right"):
                # `\not` belongs to the relation after it: treat it as one
                prev_rel = is_rel or name == "not"
            if depth == 0 and not script and name in _SPACE_CMDS and "".join(cur).strip():
                pieces.append("".join(cur))            # a break after an explicit space
                cur = []
                prev_rel = False
            script = False
            i = j
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth = max(0, depth - 1)
        elif c in "^_":
            cur.append(c)
            script = True
            i += 1
            continue
        elif depth == 0 and not script and c in _REL_CHARS:
            if not prev_rel and "".join(cur).strip():
                pieces.append("".join(cur))
                cur = []
            cur.append(c)
            prev_rel = True
            i += 1
            continue
        if depth == 0 and not script and not c.isspace() and c not in "{}":
            prev_rel = False
        cur.append(c)
        if not c.isspace():
            script = False if c != "{" else script
        i += 1
    pieces.append("".join(cur))
    pieces = [p for p in pieces if p.strip()]
    return pieces if len(pieces) > 1 else [tex]


def _emit_items(nodes, style: TextStyle, out: list, env: _Env, mark=None, gate=None) -> None:
    for n in nodes or []:
        t = n.get("type")
        if t == "text":
            out.extend(_words_from_run(_collapse_ws(n.get("value", "")), style, env, mark, gate))
        elif t == "math":
            parts = [] if n.get("marks") else _split_relations(n.get("tex", ""))
            if len(parts) > 1:
                boxes = [_math_box({"tex": p}, style, env, mark, gate) for p in parts]
                if all(b is not None for b in boxes):
                    # TeX's thick space (5mu) before each relation is a break
                    # opportunity: at a line end it vanishes, as in MathJax
                    thick = 5.0 / 18.0 * style.size * env.math_scale
                    for k, b in enumerate(boxes):
                        if k:   # before a relation: TeX's thick space; after `\,`: none
                            spaced = _ends_in_space(parts[k - 1])
                            out.append(_Glue(0.0 if spaced else thick, math=True))
                        out.append(b)
                    continue
            box = _math_box(n, style, env, mark, gate)
            if box is not None:
                out.append(box)
            elif n.get("tex", "").strip():   # a LaTeX error: show the source, flagged
                out.extend(_words_from_run("$" + n["tex"] + "$",
                                           style.derive(is_mono=True, color=style.bad_ink,
                                                        bg=style.bad_bg, size=style.size * 0.9, pad=0.2),
                                           env, mark, gate))
        elif t == "mark":
            g = steps.combine(gate, steps.gate_of(n)) if n.get("reveal") else gate
            _emit_items(n.get("content", []), _span_style(style, n.get("style")), out, env,
                        n.get("name") or mark, g)
        elif t == "span":
            g = steps.combine(gate, steps.gate_of(n)) if n.get("reveal") else gate
            _emit_items(n.get("content", []), _span_style(style, n.get("style")), out, env, mark, g)
        elif t == "strong":
            _emit_items(n.get("content", []), style.derive(weight="bold"), out, env, mark, gate)
        elif t == "emph":
            _emit_items(n.get("content", []), style.derive(italic=not style.italic), out, env, mark, gate)
        elif t == "code":
            cs = style.derive(is_mono=True, color=style.code_color, bg=style.code_panel,
                              size=style.size * 0.9, pad=0.2)   # CSS: 0.9em, padding 0 .2em
            out.extend(_words_from_run(_collapse_ws(n.get("value", "")), cs, env, mark, gate))
        elif t == "link":
            _emit_items(n.get("content", []), style.derive(color=style.link_color, underline=True),
                        out, env, mark, gate)
        elif t == "xref":
            # resolved by the emitter (`text`); unresolved → a flagged @target
            txt = n.get("text")
            link = style.derive(color=style.link_color, underline=True)   # an <a> in the HTML deck
            if n.get("content"):
                _emit_items(n["content"], link, out, env, mark, gate)
            elif txt:
                out.extend(_words_from_run(txt, link, env, mark, gate))
            else:
                out.extend(_words_from_run("@" + str(n.get("target", "")),
                                           style.derive(color=style.bad_ink, bg=style.bad_bg, pad=0.2),
                                           env, mark, gate))
        elif t == "cite":
            if n.get("prefix"):
                _emit_items(n["prefix"], style, out, env, mark, gate)
            for key in n.get("missing", []):
                out.extend(_words_from_run("@" + key, style.derive(color=style.bad_ink, bg=style.bad_bg,
                                                                   pad=0.2), env, mark, gate))
            if n.get("text"):
                sup = style.derive(color=style.link_color, size=style.size * _SUP_SIZE,
                                   rise=style.rise + _SUP_RISE * style.size)
                out.extend(_words_from_run(n["text"], sup, env, mark, gate))
        elif t == "strike":
            _emit_items(n.get("content", []), style.derive(strike=True), out, env, mark, gate)
        elif t == "underline":
            _emit_items(n.get("content", []), style.derive(underline=True), out, env, mark, gate)
        elif t == "break":
            out.append(_Break())
        elif "content" in n:
            _emit_items(n["content"], style, out, env, mark, gate)
        elif "value" in n:
            out.extend(_words_from_run(n["value"], style, env, mark, gate))


# --------------------------------------------------------------------------
# line breaking + line boxes
# --------------------------------------------------------------------------


def _collapse_glue(items: list) -> list:
    """A space following a space (across inline elements too) adds nothing —
    only zero-width break opportunities may sit next to a real space."""
    out: list = []
    for it in items:
        if isinstance(it, _Glue) and out and isinstance(out[-1], _Glue) and not (it.math or out[-1].math):
            if it.width > 0 and out[-1].width == 0:
                out[-1] = it                      # the real space wins over a bare break point
            continue
        out.append(it)
    return out


def _break_lines(items: list, wrap_em: float) -> list:
    """Greedy line breaking at glue only. Returns lines, each a list of
    ``(box, x)``; a trailing space never counts toward a line's width."""
    lines: list = []
    line: list = []
    x = 0.0
    glue = 0.0
    word: list = []

    def close():
        nonlocal line, x, glue
        lines.append(line)
        line, x, glue = [], 0.0, 0.0

    def place_word():
        nonlocal x, glue, word
        if not word:
            return
        ww = sum(b.width for b in word)
        if line and x + glue + ww > wrap_em + 1e-9:
            close()
        elif line:
            x += glue
        glue = 0.0
        for b in word:
            line.append((b, x))
            x += b.width
        word = []

    for it in items:
        if isinstance(it, _Box):
            word.append(it)
        elif isinstance(it, _Glue):
            place_word()
            if line:
                glue += it.width
        else:  # _Break
            place_word()
            close()
    place_word()
    if line or not lines:
        close()
    return lines


def layout_block(nodes, style: TextStyle, wrap_em: float, line_height: float = LINE_HEIGHT,
                 align: str = "left", math_scale: "float | None" = None) -> Laid:
    """Lay out an inline node list as one block of wrapped lines (see module doc).
    ``wrap_em`` is the line width in em of ``style``'s font; ``line_height`` the
    CSS line-height factor."""
    env = _Env(line_height, math_scale if math_scale is not None else math_scale_for(style.font))
    items: list = []
    _emit_items(nodes, style, items, env)
    if not any(isinstance(it, _Box) for it in items):
        return Laid([], 0.0, 0.0, 0.0, [])
    lines = _break_lines(_collapse_glue(items), wrap_em)
    strut_a, strut_d = _extent(style.derive(size=1.0, rise=0.0), line_height)

    pieces: list = []
    baselines: list = []
    cursor = 0.0
    widest = 0.0
    for line in lines:
        above = max([strut_a] + [b.asc for b, _ in line])
        below = max([strut_d] + [b.desc for b, _ in line])
        base = cursor + above
        cursor = base + below
        baselines.append(base)
        lw = (line[-1][1] + line[-1][0].width) if line else 0.0
        widest = max(widest, lw)
        if align == "center" and wrap_em < 1e5:
            dx = (wrap_em - lw) / 2.0
        elif align == "right" and wrap_em < 1e5:
            dx = wrap_em - lw
        else:
            dx = 0.0
        by = -(base - baselines[0])
        for box, bx in line:
            shift = np.array([bx + dx, by])
            for sps, cls, col, mark, gate in box.pieces:
                pieces.append(([sp + shift for sp in sps], cls, col, mark, gate))
    first = baselines[0] if baselines else 0.0
    return Laid(pieces, cursor, first, widest, [b - first for b in baselines])


def layout_inline(nodes, style: TextStyle, wrap_em: float, line_spacing: "float | None" = None) -> list:
    """Compatibility wrapper: just the pieces of :func:`layout_block`
    (``(subpaths, closed, fill, mark, gate)``)."""
    return layout_block(nodes, style, wrap_em).pieces
