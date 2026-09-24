"""emit-svg — build-time SVG slide emitter.

Parse a `.lmr`, lay every slide out in its design box, typeset the text with
Pango and the maths with LaTeX/dvisvgm, bake everything to deduplicated SVG
outlines, and write ONE self-contained `.html` — no MathJax, no web fonts,
nothing fetched at display time (plans/Plan-SVG.md).

The block layout reproduces the HTML deck's CSS box model (``assets/base.css``)
so a deck looks the same through either emitter: vertical margins that collapse
between siblings, CSS line boxes (``line-height`` × font size, half-leading),
list indentation and markers, and the flex behaviour of ``.middle`` slides and
``!gap fill`` (no margin collapsing, content centred / pushed down). Sizes are
in design-box px; ``F`` below is the body font size.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field, replace
from typing import Optional

import numpy as np

from ..layout import diag
from ..layout.inline import LINE_HEIGHT, Laid, TextStyle, layout_block, layout_inline, math_scale_for
from ..layout.steps import ALWAYS, combine, first_step, from_range, gate_of, parse_spec
from ..master import (Design, Region, css_theme_design, default_design, find_theme_dir,
                      resolve_design, theme_design, theme_names)
from ..parser import LemurError, Parser, deck_to_ast, load_lines
from ..render.svgdoc import Defs, Slide
from ..typeset import latex, pango
from ..typeset.geometry import bbox_of, fmt, set_precision

W, H = 1920, 1080  # design box (the SVG viewBox / coordinate space)

#: `--quality` level -> emitted coordinate decimals (geometry.PRECISION). Output
#: is vector at every level; higher = crisper under print/deep-zoom + bigger file.
_QUALITY = {"draft": 2, "low": 3, "medium": 4, "high": 5, "max": 6}

#: CSS ``line-height`` of everything that is not running text (headings,
#: captions, table cells, code, environment heads, chrome).
LH_BLOCK = 1.4

#: Annotation band geometry of the HTML runtime (design px).
ANN_TOP_PAD, ANN_ROW_HEIGHT, ANN_PAD, ARROW_STANDOFF = 21.0, 60.0, 12.0, 9.0


# --------------------------------------------------------------------------
# AST helpers
# --------------------------------------------------------------------------


def inline_text(nodes) -> str:
    """Flatten an inline node list to plain text (for footers, labels, the
    page title): structure is dropped, the words are kept."""
    parts = []
    for n in nodes or []:
        t = n.get("type")
        if t == "text":
            parts.append(n.get("value", ""))
        elif t == "math":
            parts.append(n.get("tex", ""))
        elif "content" in n:
            parts.append(inline_text(n["content"]))
        elif "value" in n:
            parts.append(n["value"])
    return " ".join(" ".join(parts).split())


def _as_inline(v) -> list:
    """An inline node list from a list, a string, or None."""
    if not v:
        return []
    if isinstance(v, str):
        return [{"type": "text", "value": v}]
    return list(v)


def _as_gate(g) -> tuple:
    """A gate from either a gate or the legacy ``(appear, until)`` pair."""
    if g is None:
        return ALWAYS
    if len(g) == 2 and not isinstance(g[0], tuple):
        return from_range(g[0] or 0, g[1])
    return tuple(g)


# --------------------------------------------------------------------------
# pieces: (subpaths, closed, fill, mark[, gate])
# --------------------------------------------------------------------------


def _hex(rgb) -> str:
    r, g, b = (max(0, min(255, round(c * 255))) for c in rgb)
    return f"#{r:02x}{g:02x}{b:02x}"


def _text_pieces(shaped, color: str):
    for cl in shaped.clusters:
        col = _hex(cl.color) if cl.color else color
        yield cl.subpaths, cl.closed, col, None


def _math_pieces(glyphs, color: str):
    for g in glyphs:
        col = g.fill if (g.fill and g.fill != "none" and g.fill != "currentColor") else color
        yield g.subpaths, g.closed, col, g.meta.get("mark")


def _style_ascent(style: TextStyle) -> float:
    """Font-metric ascent (em) for a style, to baseline-align its text blocks."""
    return pango.font_metrics(style.family, style.weight, style.italic)[0]


def _emit_block(slide: Slide, pieces, fs: float, top: float, region: tuple,
                gate: tuple = (0, None), align: str = "left", ascent: "float | None" = None) -> float:
    """Place a block's pieces and return its height in px (the template helper
    behind :func:`line`; flowed content uses the CSS line boxes of
    :func:`layout_block` instead).

    Horizontally, the ink bbox is left-aligned/centred/right-aligned in the
    region. Vertically, the first baseline sits at ``top + ascent`` (a font
    metric), so blocks with different ascenders still align; ``ascent=None``
    falls back to the bbox top."""
    rx, rw = region
    pieces = list(pieces)
    all_sp = [sp for p in pieces for sp in p[0] if len(sp)]
    if not all_sp:
        return 0.0
    minx, miny, maxx, maxy = bbox_of(all_sp)
    width = (maxx - minx) * fs
    a = maxy if ascent is None else ascent
    height = (a - miny) * fs
    if align == "center":
        x_left = rx + (rw - width) / 2
    elif align == "right":
        x_left = rx + (rw - width)
    else:
        x_left = rx
    x0 = x_left - minx * fs
    y0 = top + a * fs  # first baseline (em y=0) sits `ascent` below the block top
    g = _as_gate(gate)
    for p in pieces:
        sps, closed, col, mark = p[:4]
        pg = p[4] if len(p) > 4 else None
        slide.place(sps, closed, fs, x0, y0, col, mark=mark, gate=combine(g, pg) if pg else g)
    return height


# --------------------------------------------------------------------------
# the flow context
# --------------------------------------------------------------------------


@dataclass
class _Fx:
    """Everything block layout needs, bundled: where to draw, the design, the
    body text style and the per-build lookups (bibliography numbers)."""
    slide: Slide
    design: Design
    style: TextStyle
    mono: str
    doc_dir: str
    math_scale: float
    bib: dict = field(default_factory=dict)

    @property
    def F(self) -> float:
        return self.design.body_size

    def at(self, **kw) -> "_Fx":
        return replace(self, **kw)


def _place(fx: _Fx, laid: Laid, fs: float, x: float, top: float, gate) -> float:
    """Draw a laid-out inline block with its first line box's top at ``top``;
    return the bottom of its last line box."""
    y0 = top + laid.top * fs
    for sps, cls, col, mark, pg in laid.pieces:
        fx.slide.place(sps, cls, fs, x, y0, col, mark=mark, gate=combine(gate, pg) if pg else gate)
    return top + laid.height * fs


def _text_block(fx: _Fx, nodes, style: TextStyle, fs: float, x: float, w: float, top: float,
                gate, align: str = "left", lh: float = LH_BLOCK) -> float:
    laid = layout_block(nodes, style, max(w, 1.0) / fs, lh, align, fx.math_scale)
    if not laid.pieces:
        return top
    return _place(fx, laid, fs, x, top, gate)


def _heading_size(fx: _Fx, node: dict) -> float:
    level = node.get("level", 2)
    return fx.F * (1.35 if level <= 1 else 1.1 if level == 2 else 1.0)


def _margins(fx: _Fx, node: dict) -> tuple:
    """A block's CSS vertical margins as ``(outer_top, inner_top, outer_bottom,
    inner_bottom)`` px. *Outer* is the element's own margin; *inner* the margin
    of a nested child that collapses through it (a list's first ``li``, MathJax's
    display container inside ``div.lmr-math``, the ``table`` inside its wrapper).
    A ``:first-child``/``:last-child`` reset removes only the outer part; in
    normal flow the two collapse (max), in a flex body they add up."""
    F, d, t = fx.F, fx.design, node.get("type")
    if t == "para":
        return F, 0.0, F, 0.0
    if t == "heading":
        return 0.0, 0.0, 0.6 * _heading_size(fx, node), 0.0
    if t == "list":
        return 0.3 * F, 0.25 * F, 0.3 * F, 0.25 * F
    if t == "math":
        return 0.4 * F, 0.7 * F, 0.4 * F, 0.7 * F   # div.lmr-math around MathJax's .7em display margin
    if t == "code":
        return 0.4 * d.code_size, 0.0, 0.4 * d.code_size, 0.0
    if t == "table":
        return 0.0, 0.5 * d.table_size, 0.0, 0.5 * d.table_size
    if t in ("figure", "plot", "embed", "anim"):
        return 0.5 * F, 0.0, 0.5 * F, 0.0
    if t in ("columns", "stack", "annotate"):
        return 0.4 * F, 0.0, 0.4 * F, 0.0
    if t == "env":
        return 0.6 * F, 0.0, 0.6 * F, 0.0
    if t == "style":
        if "frame" in _classes(node):           # a border stops margins collapsing through
            return 0.6 * F, 0.0, 0.6 * F, 0.0
        body = node.get("body", [])             # no padding/border: the children's collapse through
        return 0.6 * F, _edge_margin(fx, body, 0), 0.6 * F, _edge_margin(fx, body, -1)
    if t == "bibliography":
        bs = 0.75 * F
        return 0.3 * bs, 0.25 * bs, 0.3 * bs, 0.25 * bs
    return 0.0, 0.0, 0.0, 0.0


def _edge_margin(fx: _Fx, body, side: int) -> float:
    """The margin the first (``side=0``) / last (``-1``) block of a container
    still has after the container's ``:first-child``/``:last-child`` reset."""
    items = [b for b in body or [] if b.get("type") not in _SKIP]
    if not items:
        return 0.0
    ot, it, ob, ib = _margins(fx, items[side])
    o, i = (ot, it) if side == 0 else (ob, ib)
    return max(o, i) if items[side].get("reveal") else i


def _eff_margin(outer: float, inner: float, gated: bool, reset: bool, flex: bool) -> float:
    """One side's effective margin. ``reset``: a first/last-child rule removed the
    element's own margin (a revealed block's step wrapper absorbs the rule, so it
    keeps both); ``flex``: a flex item keeps its own margin *and* contains its
    children's (a revealed block's wrapper collapses them first)."""
    if flex:
        return max(outer, inner) if gated else outer + inner
    if reset and not gated:
        return inner
    return max(outer, inner)


# --------------------------------------------------------------------------
# block flow — CSS-like vertical stacking, recursively
# --------------------------------------------------------------------------


_SKIP = ("notes", "connect", "pagebreak")


def _has_fill(blocks) -> bool:
    return any(b.get("type") == "spacer" and b.get("size") == "fill" for b in blocks or [])


def _em_px(size, F: float) -> float:
    """A spacer size (`2em`, `24px`, `1.5rem`, `3`) → px; bare/blank → one em."""
    m = re.match(r"([\d.]+)\s*(em|rem|px|ex)?$", str(size or "").strip())
    if not m:
        return F
    v = float(m.group(1))
    unit = m.group(2) or "px"
    return v * F if unit in ("em", "rem") else v * F * 0.5 if unit == "ex" else v


def _flow_blocks(fx: _Fx, blocks, x: float, w: float, top: float, gate=ALWAYS,
                 align: str = "left", rbottom: "float | None" = None, lead: float = 0.0,
                 first_zero=False, collapse: bool = True, last_reset: bool = False) -> tuple:
    """Flow ``blocks`` into the column ``[x, x+w]`` from ``top``.

    Returns ``(bottom, trailing_margin)`` — the bottom of the last block's box
    and its (uncollapsed) bottom margin, which the caller decides about.
    ``lead`` is a margin already pending above the first block (e.g. the slide
    title's); ``first_zero`` applies a container's ``:first-child { margin-top:
    0 }`` to the first block (``"ungated"``: only if it is not revealed on a step,
    whose wrapper would take the rule instead), ``last_reset`` the matching
    ``:last-child`` rule to the returned trailing margin; ``collapse=False`` is
    flex layout, where sibling margins add up. ``rbottom`` is the region's bottom: a ``!gap fill``
    (flex only) pushes what follows it down to it, and an ``!anim`` with the
    default ``body`` viewport fills the space above it."""
    items = [b for b in blocks or [] if b.get("type") not in _SKIP]
    pen, pending, first = top, lead, True
    flex = not collapse
    last_bottom = (0.0, 0.0, False)        # the last block's (outer, inner) bottom + gated
    for i, node in enumerate(items):
        t = node.get("type")
        g = combine(gate, gate_of(node))
        if t == "spacer":
            if node.get("size") == "fill":
                if rbottom is not None and not collapse:
                    rest_h, rest_trail = _measure(fx, items[i + 1:], x, w, align, collapse=False)
                    pen = max(pen + pending, rbottom - rest_h - rest_trail)
                    pending, first = 0.0, False
                continue                 # outside a flex body a fill gap has no height
            gap = pending if collapse else pending
            pen = pen + gap + _em_px(node.get("size"), fx.F)
            pending, first = 0.0, False
            continue
        ot, it, ob, ib = _margins(fx, node)
        gated = bool(node.get("reveal"))
        # `:first-child { margin-top: 0 }` — in the HTML deck a revealed block
        # sits in a step <div>; with ``"ungated"`` (the env-body/style rule) that
        # wrapper takes the rule and the block keeps its margin, otherwise (the
        # column/layer rule reaches into the wrapper) only its own margin goes
        reset = bool(first and first_zero)
        if reset and first_zero == "all":   # the container already took this margin
            mt = 0.0
        else:
            mt = _eff_margin(ot, it, gated and first_zero == "ungated", reset, flex)
        y = pen + (max(pending, mt) if collapse else pending + mt)
        bottom = _render_block(fx, node, x, w, y, g, align, rbottom)
        if bottom is None:               # nothing drawn (unknown/empty): no box
            continue
        pen, first = bottom, False
        pending = _eff_margin(ob, ib, gated, False, flex)
        last_bottom = (ob, ib, gated)
    if last_reset and not first:
        ob, ib, gated = last_bottom
        pending = 0.0 if last_reset == "all" else _eff_margin(ob, ib, gated, True, flex)
    return pen, pending


def _measure(fx: _Fx, blocks, x: float, w: float, align: str = "left", collapse: bool = True,
             first_zero=True, lead: float = 0.0, last_reset: bool = False) -> tuple:
    """``(height, trailing_margin)`` of ``blocks`` laid out in a throwaway slide
    (nothing is drawn, nothing is reported)."""
    scratch = fx.at(slide=Slide(fx.slide.w, fx.slide.h, fx.slide.bg))
    with diag.muted():
        bottom, trail = _flow_blocks(scratch, blocks, x, w, 0.0, ALWAYS, align, None, lead,
                                     first_zero, collapse, last_reset)
    return bottom, trail


def _render_block(fx: _Fx, node: dict, x: float, w: float, y: float, g, align: str,
                  rbottom: "float | None"):
    t = node.get("type")
    F = fx.F
    if t == "para":
        return _text_block(fx, node.get("content"), fx.style, F, x, w, y, g, align, fx.design.line_height)
    if t == "heading":
        hs = _heading_size(fx, node)
        st = fx.style.derive(weight=int(fx.design.title_weight), color=fx.design.title,
                             letter_spacing=fx.design.title_spacing)
        return _text_block(fx, node.get("content"), st, hs, x, w, y, g, align, LH_BLOCK)
    if t == "list":
        return _b_list(fx, node, x, w, y, g, align)
    if t == "math":
        return _b_math(fx, node, x, w, y, g)
    if t == "code":
        return _b_code(fx, node, x, w, y, g)
    if t == "table":
        return _b_table(fx, node, x, w, y, g)
    if t == "figure":
        return _b_figure(fx, node, x, w, y, g)
    if t == "embed":
        fb = node.get("fallback")
        if fb:
            return _b_figure(fx, fb, x, w, y, g)
        diag.warn("an !embed without a static fallback cannot be baked to SVG — skipped")
        return None
    if t == "plot":
        return _emit_plot(fx, node, x, w, y, g)
    if t == "anim":
        return _emit_anim(fx.slide, node, fx.design, y, (x, w), g, fx.doc_dir, rbottom)
    if t == "shader":
        return _emit_shader(fx, node, x, w, y, g, rbottom)
    if t == "columns":
        return _b_columns(fx, node, x, w, y, g, align)
    if t == "stack":
        return _b_stack(fx, node, x, w, y, g, align)
    if t == "env":
        return _b_env(fx, node, x, w, y, g, align)
    if t == "style":
        return _b_style(fx, node, x, w, y, g, align)
    if t == "bibliography":
        return _b_bibliography(fx, node, x, w, y, g, align)
    if t == "annotate":
        return _b_annotate(fx, node, x, w, y, g)
    diag.warn(f"unknown block type {t!r} — skipped")
    return None


# -- lists --------------------------------------------------------------------


def _circle_sub(cx: float, cy: float, r: float, reverse: bool = False):
    k = 0.5523 * r
    pts = [(cx + r, cy), (cx + r, cy + k), (cx + k, cy + r), (cx, cy + r),
           (cx - k, cy + r), (cx - r, cy + k), (cx - r, cy),
           (cx - r, cy - k), (cx - k, cy - r), (cx, cy - r),
           (cx + k, cy - r), (cx + r, cy - k), (cx + r, cy)]
    a = np.array(pts, float)
    return a[::-1].copy() if reverse else a


def _marker(fx: _Fx, kind: str, n: int, tx: float, base: float, gate, color: str,
            style: "TextStyle | None" = None, fs: "float | None" = None) -> None:
    """A list marker outside the item, like a browser's ``list-style-position:
    outside``: ``disc``/``circle``/``square`` shapes, or ``N.`` for ordered."""
    fs = fs or fx.F
    if kind == "decimal":
        st = style or fx.style
        laid = layout_block([{"type": "text", "value": f"{n}."}], st.derive(color=color), 1e6,
                            LH_BLOCK, "left", fx.math_scale)
        if laid.pieces:
            x = tx - 0.28 * fs - laid.width * fs
            for sps, cls, col, _m, _g in laid.pieces:
                fx.slide.place(sps, cls, fs, x, base, col, gate=gate)
        return
    r = 0.155
    cy = 0.27
    cx = -0.72
    if kind == "square":
        from ..layout.inline import _rect_sub
        sub = [_rect_sub(cx - r * 0.9, cx + r * 0.9, cy - r * 0.9, cy + r * 0.9)]
        closed = [True]
    elif kind == "circle":
        rc, cyc = 0.2, 0.33
        sub = [_circle_sub(cx, cyc, rc), _circle_sub(cx, cyc, rc - 0.045, reverse=True)]
        closed = [True, True]
    else:
        sub = [_circle_sub(cx, cy, r)]
        closed = [True]
    fx.slide.place(sub, closed, fs, tx, base, color, gate=gate)


_UL_KINDS = ("disc", "circle", "square")


def _b_list(fx: _Fx, node: dict, x: float, w: float, top: float, gate, align: str,
            level: int = 0) -> float:
    """``ul``/``ol``: ``margin: .3em 0 .3em 1.2em`` plus the 40px list padding;
    items ``margin: .25em 0`` (collapsing), ``line-height`` 1.45. A sublist is a
    nested list under its item (sharing the item's gate), one level deeper."""
    F = fx.F
    indent = 1.2 * F + 40.0
    tx, tw = x + indent, max(w - indent, F)
    ordered = bool(node.get("ordered"))
    kind = "decimal" if ordered else _UL_KINDS[min(level, 2)]
    lh = fx.design.line_height
    y, pending = top, None
    for i, item in enumerate(node.get("items", []), 1):
        g = combine(gate, gate_of(item))
        if pending is not None:
            y += max(pending, 0.25 * F)
        laid = layout_block(item.get("content", []), fx.style, tw / F, lh, align, fx.math_scale)
        if laid.pieces:
            base = y + laid.top * F
            bottom = _place(fx, laid, F, tx, y, g)
        else:                                    # an empty item still has its line
            a, d = pango.font_metrics(fx.style.font)
            base = y + (a + (lh - (a + d)) / 2) * F
            bottom = y + lh * F
        _marker(fx, kind, i, tx, base, g, fx.style.color)
        y, pending = bottom, 0.25 * F
        sub = item.get("sublist")
        if sub and sub.get("items"):
            y += max(pending, 0.3 * F)
            y = _b_list(fx, sub, tx, tw, y, g, align, level + 1)
            pending = 0.3 * F
    return y


def _b_bibliography(fx: _Fx, node: dict, x: float, w: float, top: float, gate, align: str) -> float:
    """``ol.lmr-bib``: an ordered list at 0.75em, numbered by the deck-wide
    citation numbers (so a bibliography split across slides keeps counting)."""
    fs = 0.75 * fx.F
    indent = 1.2 * fs + 40.0
    tx, tw = x + indent, max(w - indent, fs)
    lh = fx.design.line_height
    y, pending = top, None
    for k, e in enumerate(node.get("entries", []), 1):
        if pending is not None:
            y += max(pending, 0.25 * fs)
        laid = layout_block(e.get("content", []), fx.style, tw / fs, lh, align, fx.math_scale)
        if not laid.pieces:
            continue
        base = y + laid.top * fs
        y = _place(fx, laid, fs, tx, y, gate)
        _marker(fx, "decimal", fx.bib.get(e.get("key"), k), tx, base, gate, fx.style.color, fs=fs)
        pending = 0.25 * fs
    return y


# -- display maths ------------------------------------------------------------


def _b_math(fx: _Fx, node: dict, x: float, w: float, top: float, gate) -> "float | None":
    tex = node.get("tex", "").strip()
    if not tex:
        return None
    d = fx.design
    try:
        glyphs, box = latex.tex_render_marked(tex, node.get("marks") or [], "display")
    except latex.LatexError as exc:
        first = next((ln for ln in str(exc).splitlines() if ln.startswith("!")), "")
        diag.warn(f"LaTeX error in a display equation — shown as source. {first}")
        st = fx.style.derive(is_mono=True, color=fx.style.bad_ink, bg=fx.style.bad_bg, size=0.8, pad=0.2)
        return _text_block(fx, [{"type": "text", "value": tex}], st, fx.F, x, w, top, gate, "center")
    all_sp = [sp for g in glyphs for sp in g.subpaths]
    if not all_sp:
        return None
    if box is not None:          # TeX's box: what MathJax sized and centred the display by
        minx, maxx, miny, maxy = 0.0, box.width, -box.depth, box.height
    else:
        minx, miny, maxx, maxy = bbox_of(all_sp)
    em_w = max(maxx - minx, 1e-6)
    fs = d.math_size * fx.math_scale
    if em_w * fs > w:                            # never overflow the column: shrink to fit
        diag.warn(f"a display equation is {em_w * fs - w:.0f}px wider than its column — scaled "
                  f"down to {100 * w / (em_w * fs):.0f}%")
        fs = w / em_w
    x0 = x + (w - em_w * fs) / 2 - minx * fs
    # MathJax 4's display container: 0.3em padding above and below a CSS line box
    # (the text strut at line-height 1.4) that holds the formula on its baseline
    F = fx.F
    pad = 0.3 * F
    a, dsc = pango.font_metrics(fx.style.font)
    half = (LH_BLOCK - (a + dsc)) / 2
    above = max((a + half) * F, maxy * fs)
    below = max((dsc + half) * F, -miny * fs)
    y0 = top + pad + above
    for sps, cls, col, mark in _math_pieces(glyphs, d.math):
        fx.slide.place(sps, cls, fs, x0, y0, col, mark=mark, gate=gate)
    return y0 + below + pad


# -- code -----------------------------------------------------------------------


def _highlight(source: str, language: str, design: Design):
    """Per-line list of ``(start_byte, end_byte, colour, italic)`` spans via
    pygments, or None if pygments/the lexer is unavailable (then code is one
    flat colour). Comments are italic, as in the HTML deck."""
    try:
        from pygments import lex
        from pygments.lexers import get_lexer_by_name
        from pygments.token import Token
    except Exception:
        return None
    try:
        lexer = get_lexer_by_name((language or "text").lower())
    except Exception:
        return None
    cats = [
        (Token.Comment, design.code_comment), (Token.Keyword.Type, design.code_type),
        (Token.Keyword, design.code_keyword), (Token.Name.Function, design.code_function),
        (Token.Name.Class, design.code_function), (Token.Name.Builtin, design.code_type),
        (Token.Literal.String, design.code_string), (Token.Literal.Number, design.code_number),
    ]

    def color_of(tt):
        for cat, col in cats:
            if tt in cat:
                return col
        return design.code

    lines: list = [[]]
    col = 0
    for tok_type, value in lex(source, lexer):
        color = color_of(tok_type)
        italic = tok_type in Token.Comment
        parts = value.split("\n")
        for j, part in enumerate(parts):
            if j > 0:
                lines.append([])
                col = 0
            if part:
                b = len(part.encode("utf-8"))
                lines[-1].append((col, col + b, color, italic))
                col += b
    return lines


def _b_code(fx: _Fx, node: dict, x: float, w: float, top: float, gate) -> float:
    """``pre.lmr-code``: 0.62em mono, line-height 1.4, padding .6em .8em, a 1px
    rule border and a 4px radius. ``:: lang[1|4-6]`` groups highlight their
    lines (and dim the rest) during their step only."""
    d = fx.design
    source = node.get("source", "").expandtabs(8)
    lines = source.split("\n")
    fs = d.code_size
    lh = LH_BLOCK * fs
    pad_y, pad_x, bw = 0.6 * fs, 0.8 * fs, 1.0
    height = 2 * bw + 2 * pad_y + lh * max(len(lines), 1)
    fx.slide.add_rect(x + 0.5, top + 0.5, w - 1, height - 1, d.code_bg, rx=4, gate=gate,
                      stroke=d.rule, stroke_width=bw)
    inner_top = top + bw + pad_y

    groups = node.get("highlights", [])
    if groups:
        gates = [combine(gate, gate_of(grp)) for grp in groups]
        appears = [first_step(gg) for gg in gates]
        order = sorted(range(len(groups)), key=lambda i: appears[i])
        for oi, gi in enumerate(order):
            a = appears[gi]
            nxt = appears[order[oi + 1]] if oi + 1 < len(order) else None
            active = combine(gate, ((a, nxt - 1 if nxt is not None else None),))
            if nxt is not None and nxt - 1 < a:
                continue
            hl = set(groups[gi].get("lines", []))
            for L in range(1, len(lines) + 1):
                ry = inner_top + (L - 1) * lh
                if L in hl:
                    fx.slide.add_rect(x + bw, ry, w - 2 * bw, lh, d.code_highlight, opacity=0.16,
                                      gate=active)
                else:                                   # dim the other lines to 32%
                    fx.slide.add_overlay(
                        f'<rect x="{fmt(x + bw)}" y="{fmt(ry)}" width="{fmt(w - 2 * bw)}" '
                        f'height="{fmt(lh)}" fill="{d.code_bg}" fill-opacity="0.68"/>', gate=active)

    spans = _highlight(source, node.get("language", ""), d)
    asc, desc = pango.font_metrics(fx.mono)
    half = (lh - (asc + desc) * fs) / 2
    lx = x + bw + pad_x
    widest = 0.0
    for i, ln in enumerate(lines):
        if not ln.strip():
            continue
        base = inner_top + i * lh + half + asc * fs
        raw = ln.encode("utf-8")
        segs = spans[i] if spans and i < len(spans) and spans[i] else [(0, len(raw), d.code, False)]
        pen = lx
        for s0, s1, col, italic in segs:
            text = raw[s0:s1].decode("utf-8", "replace")
            if not text:
                continue
            shaped = pango.shape(text, font=fx.mono, italic=italic)
            for cl in shaped.clusters:
                fx.slide.place(cl.subpaths, cl.closed, fs, pen, base, col, gate=gate)
            pen += sum(cl.x_advance for cl in shaped.clusters) * fs
        widest = max(widest, pen - lx)
    if widest > w - 2 * (bw + pad_x) + 1:
        diag.warn(f"a code line is {widest - (w - 2 * (bw + pad_x)):.0f}px wider than its block")
    return top + height


# -- tables ---------------------------------------------------------------------


def _b_table(fx: _Fx, node: dict, x: float, w: float, top: float, gate) -> float:
    """A CSS ``border-collapse`` table at 0.85em: cells padded ``.25em .7em``,
    line-height 1.4, vertically centred; a 2px accent rule under the header, the
    ``===``/``---`` separators as 2px ink / 1px rule borders; the caption below
    (0.8em, muted); centred in the column, shrunk to fit if too wide."""
    d = fx.design
    cols = node.get("columns", [])
    n = len(cols)
    if not n:
        return None
    fs = d.table_size
    pad_x, pad_y = 0.7 * fs, 0.25 * fs
    show_head = node.get("header", True) is not False
    head_st = fx.style.derive(weight="bold")
    rows = [r for r in node.get("rows", [])]

    def lay(cell, st, wrap_em, al="left"):
        return layout_block(cell, st, wrap_em, LH_BLOCK, al, fx.math_scale)

    # CSS automatic table layout: every column gets at least its min-content
    # width (its longest word) and at most its max-content width (unwrapped);
    # when the table must wrap, the room left over after the minima is shared in
    # proportion to how much more each column would like
    mins, maxs = [0.0] * n, [0.0] * n

    def measure(c, cell, st):
        mins[c] = max(mins[c], lay(cell, st, 1e-3).width * fs)
        maxs[c] = max(maxs[c], lay(cell, st, 1e6).width * fs)

    if show_head:
        for c in range(n):
            measure(c, cols[c].get("heading", []), head_st)
    for row in rows:
        if "separator" in row:
            continue
        cells = row.get("cells", [])
        if len(cells) != n:
            diag.warn(f"a table row has {len(cells)} cells for {n} columns")
        for c, cell in enumerate(cells[:n]):
            measure(c, cell, fx.style)
    extra = 2 * pad_x + 1.0
    mins = [m + extra for m in mins]
    maxs = [max(m + extra, lo) for m, lo in zip(maxs, mins)]
    if sum(maxs) <= w:
        colw = maxs
    elif sum(mins) >= w:
        colw = mins
        diag.warn(f"a table is {sum(mins) - w:.0f}px wider than its column even fully wrapped")
    else:
        want = sum(mx - mn for mx, mn in zip(maxs, mins)) or 1.0
        room = w - sum(mins)
        colw = [mn + (mx - mn) * room / want for mx, mn in zip(maxs, mins)]
    table_w = sum(colw)
    tx = x + (w - table_w) / 2
    xs, cx = [], tx
    for cw in colw:
        xs.append(cx)
        cx += cw

    y = top
    title = node.get("title")
    if title:
        y = _text_block(fx, title, fx.style.derive(weight=600), fx.F, x, w, y, gate, "center") + 0.5 * fs

    def place_row(cells, st, y0) -> float:
        lays = []
        for c in range(n):
            al = cols[c].get("align") or "left"
            al = {"l": "left", "r": "right", "c": "center"}.get(al, al)
            lays.append((lay(cells[c] if c < len(cells) else [], st, max(colw[c] - 2 * pad_x, 1) / fs, al), al))
        inner = max([lt.height * fs for lt, _ in lays] + [LH_BLOCK * fs])
        for c, (lt, _al) in enumerate(lays):
            if lt.pieces:
                off = (inner - lt.height * fs) / 2
                _place(fx, lt, fs, xs[c] + pad_x, y0 + pad_y + off, gate)
        return y0 + inner + 2 * pad_y

    if show_head:
        y = place_row([c.get("heading", []) for c in cols], head_st, y)
        fx.slide.add_rect(tx, y, table_w, 2.0, d.accent, gate=gate)
        y += 2.0
    border = None
    for row in rows:
        if "separator" in row:
            border = row["separator"]
            continue
        if border:
            strong = border == "strong"
            th = 2.0 if strong else 1.0
            fx.slide.add_rect(tx, y, table_w, th, d.body if strong else d.rule, gate=gate)
            y += th
            border = None
        y = place_row(row.get("cells", []), fx.style, y)

    cap = node.get("caption")
    if cap:
        cfs = 0.8 * fs
        y = _text_block(fx, cap, fx.style.derive(color=d.caption), cfs, tx, table_w, y + 0.4 * cfs,
                        gate, "center")
    return y


# -- figures ----------------------------------------------------------------------


def _len_px(v, F: float = 40.0) -> "float | None":
    """A CSS length (`320px`, `320`, `12em`, `4in`, `10cm`, `24pt`) → px."""
    if v is None or v == "":
        return None
    m = re.match(r"\s*([\d.]+)\s*(px|em|rem|pt|pc|in|cm|mm)?\s*$", str(v))
    if not m:
        return None
    x = float(m.group(1))
    return x * {None: 1.0, "px": 1.0, "em": F, "rem": F, "pt": 96 / 72, "pc": 16.0,
                "in": 96.0, "cm": 96 / 2.54, "mm": 96 / 25.4}[m.group(2)]


def _pct(v, default: float) -> float:
    """A width given as a fraction of the column (`60%`) → 0..1; px → of 1728."""
    if not v:
        return default
    s = str(v).strip()
    if s.endswith("%"):
        try:
            return max(min(float(s[:-1]) / 100.0, 1.0), 0.02)
        except ValueError:
            return default
    px = _len_px(s)
    return min(px / (W - 192), 1.0) if px else default


def _image_size(path: str) -> "tuple | None":
    """Intrinsic ``(w, h)`` in CSS px: SVG width/height (else viewBox), and the
    PNG/GIF/JPEG/WebP headers."""
    ext = os.path.splitext(path)[1].lower()
    try:
        if ext == ".svg":
            root = ET.parse(path).getroot()
            w, h = _len_px(root.get("width")), _len_px(root.get("height"))
            if w and h:
                return w, h
            vb = root.get("viewBox")
            if vb:
                p = [float(v) for v in vb.replace(",", " ").split()]
                return p[2], p[3]
            return None
        import struct
        with open(path, "rb") as fh:
            head = fh.read(32)
            if head[:8] == b"\x89PNG\r\n\x1a\n":
                return tuple(float(v) for v in struct.unpack(">II", head[16:24]))
            if head[:6] in (b"GIF87a", b"GIF89a"):
                return tuple(float(v) for v in struct.unpack("<HH", head[6:10]))
            if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
                fh.seek(12)
                chunk = fh.read(30)
                if chunk[:4] == b"VP8X":
                    w = 1 + int.from_bytes(chunk[12:15], "little")
                    h = 1 + int.from_bytes(chunk[15:18], "little")
                    return float(w), float(h)
                if chunk[:4] == b"VP8 ":
                    w, h = struct.unpack("<HH", chunk[14:18])
                    return float(w & 0x3FFF), float(h & 0x3FFF)
                if chunk[:4] == b"VP8L":
                    b = chunk[9:13]
                    w = 1 + (((b[1] & 0x3F) << 8) | b[0])
                    h = 1 + (((b[3] & 0xF) << 10) | (b[2] << 2) | ((b[1] & 0xC0) >> 6))
                    return float(w), float(h)
            if head[:2] == b"\xff\xd8":                 # JPEG: walk to a SOF marker
                fh.seek(2)
                while True:
                    m = fh.read(2)
                    if len(m) < 2 or m[0] != 0xFF:
                        return None
                    if m[1] in (0xD8, 0x01) or 0xD0 <= m[1] <= 0xD7:
                        continue
                    ln = struct.unpack(">H", fh.read(2))[0]
                    if m[1] in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB,
                                0xCD, 0xCE, 0xCF):
                        fh.read(1)
                        h, w = struct.unpack(">HH", fh.read(4))
                        return float(w), float(h)
                    fh.seek(ln - 2, 1)
    except Exception:
        return None
    return None


#: When set (during a "separate images" build), maps an image path to an href
#: and copies the file out, instead of embedding it as a data-URI.
_IMG_SINK = None

_MIME = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".gif": "image/gif",
         ".webp": "image/webp", ".svg": "image/svg+xml", ".avif": "image/avif", ".bmp": "image/bmp"}


def _data_uri(path: str) -> str:
    mime = _MIME.get(os.path.splitext(path)[1].lower(), "application/octet-stream")
    with open(path, "rb") as fh:
        b64 = base64.b64encode(fh.read()).decode("ascii")
    return f"data:{mime};base64,{b64}"


def _image_href(path: str) -> "str | None":
    """The href for an image file (embedded, or copied out); None if it can't be
    read — the caller reports it."""
    try:
        return (_IMG_SINK or _data_uri)(path)
    except OSError:
        return None


def _missing_image(fx: _Fx, src: str, x: float, y: float, w: float, h: float, gate) -> None:
    """A visible placeholder for an image that could not be read."""
    fx.slide.add_rect(x, y, w, h, "#fff4f4", rx=6, gate=gate, stroke="#c0392b", stroke_width=2)
    st = fx.style.derive(color="#c0392b", size=0.6)
    _text_block(fx, [{"type": "text", "value": f"missing image: {src}"}], st, fx.F, x + 12, w - 24,
                y + h / 2 - 0.6 * fx.F, gate, "center")


def _b_figure(fx: _Fx, node: dict, x: float, w: float, top: float, gate) -> "float | None":
    """``figure.lmr-figure``: centred; unsized, one image keeps its natural size
    capped to the column and 560px high; ``!width`` is a fraction of the column
    (the image fills it); several ``!src`` layers share one box, each revealed on
    its own step (``!mode replace`` hides a layer when the next one arrives).
    The caption sits under it at 0.7em, muted."""
    sources = [s for s in (node.get("sources") or []) if s]
    if not sources:
        return None
    d, F = fx.design, fx.F
    replace_mode = node.get("mode") == "replace"
    sized_w = node.get("width")
    sized_h = _len_px(node.get("height"), F) if node.get("height") and not str(node.get("height")).endswith("%") else None
    layers = node.get("layers") or []

    infos = []
    for src in sources:
        path = os.path.join(fx.doc_dir, src)
        size = _image_size(path) if os.path.isfile(path) else None
        href = _image_href(path) if os.path.isfile(path) else None
        if href is None:
            diag.warn(f"image not found or unreadable: {src}")
        infos.append((src, href, size))

    ar0 = next((s[0] / s[1] for _, _, s in infos if s and s[1]), 1.6)
    if len(sources) == 1:
        size = infos[0][2]
        if sized_w:
            dw = w * _pct(sized_w, 1.0)
            dh = dw / ar0
        elif sized_h:
            dh = sized_h
            dw = min(dh * ar0, w)
            dh = dw / ar0
        else:
            nat_w = size[0] if size else w * 0.7
            dw = min(nat_w, w)
            dh = dw / ar0
            if dh > 560.0:
                dh = 560.0
                dw = dh * ar0
    else:
        dw = w * _pct(sized_w, 1.0) if sized_w else w
        dh = dw / ar0
        if sized_h and not sized_w:
            dh = sized_h
            dw = min(dh * ar0, w)
            dh = dw / ar0

    # one gate per layer: the first uses the block's, the rest their own spec
    gates = [gate]
    for i in range(1, len(sources)):
        spec = layers[i - 1] if i - 1 < len(layers) else None
        if spec:
            gates.append(combine(gate, gate_of({"reveal": spec})))
        else:
            gates.append(combine(gate, ((first_step(gate) + i, None),)))
    if replace_mode and len(sources) > 1:
        for i in range(len(sources) - 1):
            nxt = first_step(gates[i + 1])
            if nxt > 0:
                gates[i] = combine(gates[i], ((0, nxt - 1),))

    fx0 = x + (w - dw) / 2
    for (src, href, size), g in zip(infos, gates):
        ar = (size[0] / size[1]) if (size and size[1]) else ar0
        lh = dw / ar
        if href is None:
            _missing_image(fx, src, fx0, top, dw, min(lh, dh), g)
        else:
            fx.slide.add_image(fx0, top, dw, lh, href, gate=g)
    bottom = top + dh

    cap = node.get("caption")
    if cap:
        cfs = d.caption_size
        # a !width figure is that wide, so its caption wraps to it; otherwise
        # the figure (a block) spans the column
        cx, cw = (fx0, dw) if sized_w else (x, w)
        bottom = _text_block(fx, cap, fx.style.derive(color=d.caption), cfs, cx, cw,
                             bottom + 0.3 * cfs, gate, "center")
    return bottom


_BUILD_MEMO: dict = {}   # per-build results of user modules (plots/anims): measured twice, run once


def _load_figure(path: str):
    """Import a `!plot` `!src` module and get its matplotlib ``Figure``: a
    ``figure()``/``plot()``/``make_figure()`` function, a module-level ``fig``, or
    the current pyplot figure the script left behind."""
    import importlib.util

    import matplotlib
    matplotlib.use("Agg")           # no display; render straight to a buffer
    import matplotlib.pyplot as plt

    plt.rcParams["svg.fonttype"] = "path"   # text as outlines → self-contained SVG
    plt.close("all")
    global _ANIM_SEQ
    _ANIM_SEQ += 1
    spec = importlib.util.spec_from_file_location(f"_lmr_plot_{_ANIM_SEQ}", path)
    if spec is None or spec.loader is None:
        raise OSError(f"cannot import plot module: {path}")
    mod = importlib.util.module_from_spec(spec)
    here = os.path.dirname(os.path.abspath(path))    # so the module can import siblings
    added = here not in sys.path
    if added:
        sys.path.insert(0, here)
    try:
        spec.loader.exec_module(mod)
    finally:
        if added:
            sys.path.remove(here)
    for name in ("figure", "plot", "make_figure"):
        fn = getattr(mod, name, None)
        if callable(fn):
            return fn()
    fig = getattr(mod, "fig", None)
    return fig if fig is not None else plt.gcf()


def _plot_svg(path: str) -> str:
    key = ("plot", path)
    if key not in _BUILD_MEMO:
        import io

        import matplotlib.pyplot as plt

        fig = _load_figure(path)
        buf = io.StringIO()
        fig.savefig(buf, format="svg", bbox_inches="tight")
        plt.close(fig)
        _BUILD_MEMO[key] = buf.getvalue()
    return _BUILD_MEMO[key]


def _emit_plot(fx: _Fx, node: dict, x: float, w: float, top: float, gate) -> "float | None":
    """Run a matplotlib `!src`, bake the figure to a self-contained SVG, and place
    it like `!img` (data-URI ``<image>`` — publication-quality axes/legends/etc.
    with text as outlines). Aspect comes from the figure's SVG viewBox."""
    src = node.get("src")
    if not src:
        return None
    path = os.path.join(fx.doc_dir, src)
    try:
        svg = _plot_svg(path)
    except Exception as exc:                          # a broken plot must not kill the deck
        diag.warn(f"!plot {src} failed: {type(exc).__name__}: {exc}")
        _missing_image(fx, src, x + w * 0.15, top, w * 0.7, w * 0.7 / 1.6, gate)
        return top + w * 0.7 / 1.6
    href = "data:image/svg+xml;base64," + base64.b64encode(svg.encode("utf-8")).decode("ascii")
    m = re.search(r'viewBox="[\d.]+ [\d.]+ ([\d.]+) ([\d.]+)"', svg)
    ar = (float(m.group(1)) / float(m.group(2))) if m and float(m.group(2)) else 1.4
    dw = w * _pct(node.get("width"), 0.7)
    dh = _len_px(node.get("height"), fx.F) or dw / ar
    fx.slide.add_image(x + (w - dw) / 2, top, dw, dh, href, gate=gate)
    bottom = top + dh
    cap = node.get("caption")
    if cap:
        cfs = fx.design.caption_size
        bottom = _text_block(fx, cap, fx.style.derive(color=fx.design.caption), cfs, x, w,
                             bottom + 0.3 * cfs, gate, "center")
    return bottom


# -- containers ---------------------------------------------------------------------


def _classes(node) -> list:
    return list(((node or {}).get("style") or {}).get("classes") or [])


def _b_columns(fx: _Fx, node: dict, x: float, w: float, top: float, gate, align: str) -> "float | None":
    """``.lmr-columns``: a flex row, ``gap: 1.6em``; widths by weight; each
    column is its own formatting context (first child's top margin dropped, the
    last child's bottom margin kept) and ``.center``/``.bottom`` align it
    vertically within the row."""
    cols = node.get("columns", [])
    if not cols:
        return None
    F = fx.F
    gap = 1.6 * F
    weights = [max(float(c.get("weight", 1) or 1), 1e-6) for c in cols]
    avail = w - gap * (len(cols) - 1)
    widths = [avail * wt / sum(weights) for wt in weights]
    xs, cx = [], x
    for cw in widths:
        xs.append(cx)
        cx += cw + gap
    heights = []
    for col, cx, cw in zip(cols, xs, widths):
        h, trail = _measure(fx, col.get("body", []), cx, cw, align)
        heights.append(h + trail)
    row_h = max(heights) if heights else 0.0
    for col, cx, cw, h in zip(cols, xs, widths, heights):
        cl = _classes(col)
        off = (row_h - h) / 2 if "center" in cl else (row_h - h) if "bottom" in cl else 0.0
        _flow_blocks(fx, col.get("body", []), cx, cw, top + off, gate, align, first_zero=True)
    return top + row_h


def _b_stack(fx: _Fx, node: dict, x: float, w: float, top: float, gate, align: str) -> "float | None":
    """``.lmr-stack``: every layer in the same box (a grid cell), each on its own
    gate; the box keeps the tallest layer so nothing below moves."""
    layers = node.get("layers", [])
    if not layers:
        return None
    heights = []
    for layer in layers:
        h, trail = _measure(fx, layer.get("body", []), x, w, align)
        heights.append(h + trail)
        _flow_blocks(fx, layer.get("body", []), x, w, top, combine(gate, gate_of(layer)), align,
                     first_zero=True)
    return top + max(heights)


_ENV_RULE = {"proof": "caption", "warning": "#c0392b"}


def _b_env(fx: _Fx, node: dict, x: float, w: float, top: float, gate, align: str) -> float:
    """``section.lmr-env``: a 3px left rule (accent; muted for a proof, red for
    a warning), padding ``.1em 0 .1em .9em``; the head reads ``Kind (Title).`` —
    the kind bold in the rule colour, the title italic; then the body, which
    holds any blocks. A proof ends with a ∎."""
    d, F = fx.design, fx.F
    kind = str(node.get("kind", "")).strip()
    rc = _ENV_RULE.get(kind, "accent")
    rule = d.caption if rc == "caption" else d.accent if rc == "accent" else rc
    bw, pad_l, pad_y = 3.0, 0.9 * F, 0.1 * F
    ix, iw = x + bw + pad_l, max(w - bw - pad_l, F)
    y = top + pad_y
    head: list = []
    if kind:
        head.append({"type": "span", "style": {"color": rule, "classes": ["bold"]},
                     "content": [{"type": "text", "value": kind[:1].upper() + kind[1:]}]})
    if node.get("title"):
        head += [{"type": "text", "value": " ("},
                 {"type": "emph", "content": list(node["title"])},
                 {"type": "text", "value": ")"}]
    if head:
        head.append({"type": "text", "value": "."})
        y = _text_block(fx, head, fx.style, F, ix, iw, y, gate, "left", LH_BLOCK)
    body = list(node.get("body", []))
    if kind == "proof" and body and body[-1].get("type") == "para":
        last = dict(body[-1])
        last["content"] = list(last.get("content", [])) + [
            {"type": "span", "style": {"color": d.caption}, "content": [{"type": "text", "value": " ∎"}]}]
        body[-1] = last
    if body:
        y, trail = _flow_blocks(fx, body, ix, iw, y + (0.15 * F if head else 0.0), gate, align,
                                first_zero="ungated", last_reset=True)
        y += trail
    y += pad_y
    fx.slide.add_rect(x, top, bw, max(y - top, 2.0), rule, gate=gate)
    return y


def _b_style(fx: _Fx, node: dict, x: float, w: float, top: float, gate, align: str) -> float:
    """``.lmr-style``: its colour/emphasis applies to the body; ``.center``
    centres it; ``.frame`` draws a 1px rule border (radius 6, padding
    ``.5em .8em``); ``bg:`` tints the box (unpadded unless framed)."""
    from ..layout.inline import _span_style
    d, F = fx.design, fx.F
    sd = node.get("style") or {}
    classes = sd.get("classes") or []
    st = _span_style(fx.style, sd)
    sub = fx.at(style=st)
    al = "center" if "center" in classes else align
    frame, bg = "frame" in classes, sd.get("bg")
    bw = 1.0 if frame else 0.0
    pad_y, pad_x = (0.5 * F, 0.8 * F) if frame else (0.0, 0.0)
    ix, iw = x + bw + pad_x, max(w - 2 * (bw + pad_x), F)
    body = node.get("body", [])
    # framed: the children's edge margins stay inside the border; unframed (plain
    # or `bg:` only): they collapse through the box into its own margin (see
    # _margins), so the content starts right at its edge
    fz, lr = ("ungated", True) if frame else ("all", "all")
    h, trail = _measure(sub, body, ix, iw, al, first_zero=fz, last_reset=lr)
    box_h = 2 * (bw + pad_y) + h + trail
    if bg:
        fx.slide.add_rect(x, top, w, box_h, bg, rx=(6 if frame else 0), gate=gate)
    if frame:
        fx.slide.add_rect(x + 0.5, top + 0.5, w - 1, box_h - 1, "none", rx=6, gate=gate,
                          stroke=d.rule, stroke_width=bw)
    _flow_blocks(sub, body, ix, iw, top + bw + pad_y, gate, al, first_zero=fz)
    return top + box_h


# -- annotate / connect: arrows at build time from real glyph boxes ------------------


def _head(tx: float, ty: float, dx: float, dy: float, color: str, length: float = 21.0,
          half: "float | None" = None) -> str:
    """A filled arrowhead triangle with its tip at ``(tx, ty)``, pointing along
    ``(dx, dy)``."""
    L = (dx * dx + dy * dy) ** 0.5 or 1.0
    ux, uy = dx / L, dy / L
    px, py = -uy, ux
    hw = length / 2 if half is None else half
    b1 = (tx - ux * length + px * hw, ty - uy * length + py * hw)
    b2 = (tx - ux * length - px * hw, ty - uy * length - py * hw)
    return (f'<path d="M{fmt(tx)},{fmt(ty)} L{fmt(b1[0])},{fmt(b1[1])} '
            f'L{fmt(b2[0])},{fmt(b2[1])} Z" fill="{color}"/>')


def _cubic_arrow(p0, c1, c2, p1, color: str, direction: str = "fwd", styles=()) -> str:
    """A cubic connector with arrowheads per ``direction`` (fwd/back/both; ``none``
    for a plain line), drawn like the HTML deck's SVG marker: a triangle six
    stroke-widths long and wide whose tip reaches 20% past the path's end.
    ``styles``: dashed / thin / thick."""
    styles = set(styles or ())
    sw = 2.0 if "thin" in styles else 6.0 if "thick" in styles else 3.5
    head = 6.0 * sw
    (x0, y0), (x1, y1) = p0, p1

    def tangent(a, b, fallback):
        vx, vy = a[0] - b[0], a[1] - b[1]
        if abs(vx) + abs(vy) < 1e-6:
            vx, vy = a[0] - fallback[0], a[1] - fallback[1]
        L = (vx * vx + vy * vy) ** 0.5 or 1.0
        return vx / L, vy / L

    d = (f"M{fmt(x0)},{fmt(y0)} C{fmt(c1[0])},{fmt(c1[1])} {fmt(c2[0])},{fmt(c2[1])} "
         f"{fmt(x1)},{fmt(y1)}")
    dash = ' stroke-dasharray="7 6"' if "dashed" in styles else ""
    parts = [f'<path d="{d}" fill="none" stroke="{color}" stroke-width="{fmt(sw)}"{dash}/>']
    if direction in ("fwd", "both"):
        ux, uy = tangent(p1, c2, p0)
        parts.append(_head(x1 + ux * 0.2 * head, y1 + uy * 0.2 * head, ux, uy, color, head))
    if direction in ("back", "both"):
        ux0, uy0 = tangent(p0, c1, p1)
        parts.append(_head(x0 + ux0 * 0.2 * head, y0 + uy0 * 0.2 * head, ux0, uy0, color, head))
    return "".join(parts)


def _arrow(ax: float, ay: float, bx: float, by: float, color: str,
           direction: str = "fwd", dashed: bool = False, bow: float = 1.0, ctrl=None) -> str:
    """A quadratic connector from A to B (kept for templates that draw their own
    arrows): bows perpendicular to the chord by ``bow``, or through ``ctrl``."""
    if ctrl is not None:
        cx, cy = ctrl
    else:
        dx, dy = bx - ax, by - ay
        L = (dx * dx + dy * dy) ** 0.5 or 1.0
        px, py = -dy / L, dx / L
        off = min(max(L * 0.28, 46.0), 150.0) * bow
        cx, cy = (ax + bx) / 2 + px * off, (ay + by) / 2 + py * off
    c1 = (ax + (cx - ax) * 2 / 3, ay + (cy - ay) * 2 / 3)
    c2 = (bx + (cx - bx) * 2 / 3, by + (cy - by) * 2 / 3)
    return _cubic_arrow((ax, ay), c1, c2, (bx, by), color, direction, ("dashed",) if dashed else ())


def _union(boxes):
    return (min(b[0] for b in boxes), min(b[1] for b in boxes),
            max(b[2] for b in boxes), max(b[3] for b in boxes))


def _b_annotate(fx: _Fx, node: dict, x: float, w: float, top: float, gate) -> float:
    """Each item recolours its mark on its step; an item **with a label** also
    places the label (0.6em italic, in the item colour) in a band below — one row
    per label, centred under the mark — with an S-curve arrow up to every
    occurrence of the mark (a reused name is a group). A label-less item is a
    colour/emphasis-only step."""
    items = node.get("items", [])
    labeled = sum(1 for it in items if it.get("label"))
    band = ANN_TOP_PAD + ANN_ROW_HEIGHT * labeled if labeled else 0.0
    fs = 0.6 * fx.F
    row = 0
    for i, item in enumerate(items):
        name = item.get("mark")
        color = item.get("color")            # the parser assigns the palette colours
        ink = color or fx.design.accent      # label + arrow (the old runtime's default)
        ig = combine(gate, gate_of(item))
        from_on = combine(gate, ((first_step(ig), None),))   # colours accumulate
        boxes = fx.slide.mark_boxes(name)
        if boxes:
            fx.slide.colorize_mark(name, color, gate=from_on, emphasis=item.get("emphasis") or ())
        else:
            diag.warn(f"!annotate: no mark named {name!r} on this slide")
        label = item.get("label")
        if not label:
            continue
        lst = fx.style.derive(color=ink, italic=True)
        laid = layout_block(label, lst, 1e6, LH_BLOCK, "left", fx.math_scale)
        if not laid.pieces:
            continue
        lw, lh = laid.width * fs, laid.height * fs
        if boxes:
            u = _union(boxes)
            cx = (u[0] + u[2]) / 2
        else:
            cx = x + w / 2
        lx = max(x + ANN_PAD, min(cx - lw / 2, x + w - lw - ANN_PAD))
        ly = top + ANN_TOP_PAD + row * ANN_ROW_HEIGHT
        row += 1
        _place(fx, laid, fs, lx, ly, from_on)
        for b in boxes:
            tcx = (b[0] + b[2]) / 2
            x0 = max(lx + 4, min(tcx, lx + lw - 4))
            below = (ly + lh / 2) >= (b[1] + b[3]) / 2
            if below:
                y0, y1 = ly, b[3] + ARROW_STANDOFF
            else:
                y0, y1 = ly + lh, b[1] - ARROW_STANDOFF
            my = (y0 + y1) / 2
            fx.slide.add_overlay(_cubic_arrow((x0, y0), (x0, my), (tcx, my), (tcx, y1), ink),
                                 gate=combine(from_on, fx.slide.mark_gate(name)))
    return top + band


def _read_glsl(path: str, seen=None) -> str:
    """A GLSL file with its ``#include "file"`` lines resolved (relative to the
    including file, each file once) — GLSL has no includes of its own."""
    seen = set() if seen is None else seen
    path = os.path.abspath(path)
    if path in seen:
        return ""
    seen.add(path)
    out = []
    with open(path, encoding="utf-8") as fh:
        for ln in fh.read().splitlines():
            m = re.match(r'\s*#\s*include\s+"([^"]+)"', ln)
            if m:
                out.append(_read_glsl(os.path.join(os.path.dirname(path), m.group(1)), seen))
            else:
                out.append(ln)
    return "\n".join(out)


#: Set during a build when a slide carries a `!shader` (render_deck then inlines
#: the WebGL player).
_USES_SHADERS = [False]
#: … and when an !anim has 3-D world shapes (then it inlines their projector).
_USES_WORLD = [False]


def _emit_shader(fx: _Fx, node: dict, x: float, w: float, top: float, gate,
                 rbottom: "float | None") -> "float | None":
    """A live GPU shader: the GLSL is inlined and a `<canvas>` placed in its
    viewport (in a `<foreignObject>`, so it scales, transitions and fades with
    the slide). The display runtime compiles and runs it (`svg/shader.js`).
    It sits in the slide's back layer — with ``!viewport full`` the slide's
    text reads on top of it."""
    src = node.get("src")
    path = os.path.join(fx.doc_dir, src or "")
    vx, vy, vw, vh = _anim_viewport(node, fx.design, top, (x, w), 16 / 9, rbottom)
    try:
        glsl = _read_glsl(path)
    except OSError:
        diag.warn(f"!shader source not found: {src}")
        _missing_image(fx, src or "?", vx, vy, vw, vh, gate)
        return vy + vh
    if "mainImage" not in glsl:
        diag.warn(f"!shader {src}: no mainImage(out vec4, in vec2) function")
    _USES_SHADERS[0] = True
    b64 = base64.b64encode(glsl.encode("utf-8")).decode("ascii")
    attrs = [f'data-glsl="{b64}"', f'data-shader-steps="{int(node.get("steps") or 0)}"']
    if node.get("sound"):
        attrs.append(f'data-sound="{_esc_attr(node["sound"])}"')
    if node.get("quality"):
        attrs.append(f'data-quality="{_esc_attr(str(node["quality"]))}"')
    fx.slide.add_back(
        f'<rect x="{fmt(vx)}" y="{fmt(vy)}" width="{fmt(vw)}" height="{fmt(vh)}" fill="#05070d"/>'
        f'<foreignObject class="lmr-shader" x="{fmt(vx)}" y="{fmt(vy)}" width="{fmt(vw)}" '
        f'height="{fmt(vh)}" {" ".join(attrs)}>'
        f'<div xmlns="http://www.w3.org/1999/xhtml" class="lmr-shader-box"></div></foreignObject>',
        gate=gate)
    if (node.get("viewport") or "body").strip() != "body":
        return None                  # full / explicit rect: behind the text, no flow space
    return vy + vh


def _esc_attr(s: str) -> str:
    return (s.replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;").replace(">", "&gt;"))


def _connect_endpoints(f, t):
    """The HTML runtime's mark-to-mark geometry: attach on the facing edges along
    the dominant axis and pull the control points along it (an S-curve)."""
    fx0, fy0, fx1, fy1 = f
    tx0, ty0, tx1, ty1 = t
    fcx, fcy = (fx0 + fx1) / 2, (fy0 + fy1) / 2
    tcx, tcy = (tx0 + tx1) / 2, (ty0 + ty1) / 2
    ox = min(fx1, tx1) - max(fx0, tx0)
    oy = min(fy1, ty1) - max(fy0, ty0)
    horizontal = (True if (oy > 0 and ox <= 0) else False if (ox > 0 and oy <= 0)
                  else abs(tcx - fcx) >= abs(tcy - fcy))
    s = ARROW_STANDOFF
    if horizontal:
        y0, y1 = fcy, tcy
        if tcx >= fcx:
            x0, x1 = fx1, tx0 - s
        else:
            x0, x1 = fx0, tx1 + s
        mx = (x0 + x1) / 2
        return (x0, y0), (mx, y0), (mx, y1), (x1, y1)
    x0, x1 = fcx, tcx
    if tcy >= fcy:
        y0, y1 = fy1, ty0 - s
    else:
        y0, y1 = fy0, ty1 + s
    my = (y0 + y1) / 2
    return (x0, y0), (x0, my), (x1, my), (x1, y1)


def _nearest(b, boxes):
    cx, cy = (b[0] + b[2]) / 2, (b[1] + b[3]) / 2
    return min(boxes, key=lambda o: ((o[0] + o[2]) / 2 - cx) ** 2 + ((o[1] + o[3]) / 2 - cy) ** 2)


def _draw_connect(fx: _Fx, node: dict, gate=ALWAYS) -> None:
    """``!connect``: an arrow between two marks per line, on that line's step and
    only while both marks are shown. A group (a reused name) pairs each
    occurrence of the larger side with its nearest counterpart."""
    slide = fx.slide
    ng = combine(gate, gate_of(node))
    for link in node.get("links", []):
        f, t = link.get("from"), link.get("to")
        fb, tb = slide.mark_boxes(f), slide.mark_boxes(t)
        missing = [n for n, b in ((f, fb), (t, tb)) if not b]
        if missing:
            diag.warn(f"!connect: no mark named {', '.join(map(repr, missing))} on this slide")
            continue
        color = link.get("color") or fx.design.accent
        styles = [s.lstrip(".") for s in (link.get("styles") or [])]
        g = combine(ng, gate_of(link), slide.mark_gate(f), slide.mark_gate(t))
        pairs = ([(a, _nearest(a, tb)) for a in fb] if len(fb) >= len(tb)
                 else [(_nearest(b, fb), b) for b in tb])
        for a, b in pairs:
            p0, c1, c2, p1 = _connect_endpoints(a, b)
            slide.add_overlay(_cubic_arrow(p0, c1, c2, p1, color, link.get("dir", "fwd"), styles), gate=g)


def _iter_connects(blocks, gate=ALWAYS):
    """Yield ``(connect_node, enclosing_gate)`` anywhere in the slide — inside
    columns, stacks, environments and styled blocks too."""
    for node in blocks or []:
        t = node.get("type")
        g = combine(gate, gate_of(node)) if t != "connect" else gate
        if t == "connect":
            yield node, gate
        elif t == "columns":
            for c in node.get("columns", []):
                yield from _iter_connects(c.get("body", []), g)
        elif t == "stack":
            for layer in node.get("layers", []):
                yield from _iter_connects(layer.get("body", []), combine(g, gate_of(layer)))
        elif t in ("env", "style"):
            yield from _iter_connects(node.get("body", []), g)


def _draw_arrows(fx: _Fx, blocks) -> None:
    # annotate is drawn in the flow (its band takes space); connect is deferred
    # to here so both of its marks exist regardless of the order they appear in.
    for node, g in _iter_connects(blocks):
        _draw_connect(fx, node, g)


# --------------------------------------------------------------------------
# !anim — a build-time animation baked into a slide viewport
# --------------------------------------------------------------------------

_ANIM_SEQ = 0            # unique clip/id counter across every slide on the page


def _load_anim(path: str) -> dict:
    """Import an `!anim` `!src` module, find its ``Anim`` subclass, and run it —
    returning the keyframe IR (``{nodes, tracks, duration, beats, camera, defs}``)."""
    import importlib.util

    from ..anim.scene import Anim, clear_registry, registered_anims

    global _ANIM_SEQ
    _ANIM_SEQ += 1
    clear_registry()
    spec = importlib.util.spec_from_file_location(f"_lmr_anim_{_ANIM_SEQ}", path)
    if spec is None or spec.loader is None:
        raise OSError(f"cannot import animation module: {path}")
    mod = importlib.util.module_from_spec(spec)
    here = os.path.dirname(os.path.abspath(path))    # so the module can import siblings
    added = here not in sys.path
    if added:
        sys.path.insert(0, here)
    try:
        spec.loader.exec_module(mod)
    finally:
        if added:
            sys.path.remove(here)
    anims = registered_anims()
    if not anims:                                    # not registered? scan the module
        anims = [v for v in vars(mod).values()
                 if isinstance(v, type) and issubclass(v, Anim) and v is not Anim]
    anims = [a for a in anims if getattr(a, "enabled", True)]   # `enabled = False` opts out
    if not anims:
        raise ValueError(f"no enabled Anim subclass found in {path}")
    return anims[-1]().render()                       # the last one defined wins


def _rgb_hex(rgb) -> str:
    """An IR colour (``[r, g, b]`` in 0..1) as ``#rrggbb``."""
    if not rgb:
        return "#ffffff"
    return "#" + "".join(f"{max(0, min(255, round(c * 255))):02x}" for c in rgb[:3])


def _flat_path(flat: list, struct: list) -> str:
    """A `d`-morph keyframe (flattened cubic points + ``struct=[[counts],[closed]]``)
    as an SVG path — the Python twin of the runtime's ``pathData`` (for baking a
    Transform's end shape)."""
    counts, closed = struct[0], struct[1]
    out, k = [], 0
    if len(struct) > 2 and struct[2]:          # a polyline: anchors only
        for s, n in enumerate(counts):
            out += [("L" if j else "M") + f"{fmt(flat[k + 2 * j])},{fmt(flat[k + 2 * j + 1])}" for j in range(n)]
            if n and closed[s]:
                out.append("Z")
            k += n * 2
        return "".join(out)
    for s, n in enumerate(counts):
        if n > 0:
            out.append(f"M{fmt(flat[k])},{fmt(flat[k + 1])}")
            i = 1
            while i + 2 < n:
                b = k + i * 2
                out.append(f"C{fmt(flat[b])},{fmt(flat[b + 1])} {fmt(flat[b + 2])},"
                           f"{fmt(flat[b + 3])} {fmt(flat[b + 4])},{fmt(flat[b + 5])}")
                i += 3
            if closed[s]:
                out.append("Z")
        k += n * 2
    return "".join(out)


def _anim_viewport(node: dict, design: Design, pen: float, region: tuple, aspect: float,
                   rbottom: "float | None") -> tuple:
    """Resolve an `!anim`'s viewport rect (slide px). ``full`` = the whole slide,
    ``"x y w h"`` = explicit, ``body`` (default) = **fill** the remaining region
    (pen → its bottom) across the full width, so the animation takes all the space
    it can and centres in it; ``!width``/``!height`` override either extent."""
    vp = (node.get("viewport") or "body").strip()
    if vp == "full":
        return 0.0, 0.0, float(design.width), float(design.height)
    parts = vp.split()
    if len(parts) == 4 and all(re.match(r"-?[\d.]+$", p) for p in parts):
        return tuple(float(p) for p in parts)
    vw = _len_px(node.get("width")) or region[1]
    # Fill down to the region bottom (the camera letterboxes the frame to fit);
    # fall back to a frame-aspect box only when we don't know the bottom.
    avail = (rbottom - pen) if rbottom is not None else vw / (aspect or 1.7777778)
    vh = _len_px(node.get("height")) or max(avail, 1.0)
    return region[0], pen, vw, vh


def _emit_anim(slide: Slide, node: dict, design: Design, pen: float, region: tuple,
               gate: tuple, doc_dir: str, rbottom: "float | None" = None) -> float:
    """Run the `!src` animation, bake its **final** frame into the viewport, and
    embed the keyframe IR (``data-anim``) for the runtime to play. The baked frame
    is the completed animation — the right thing for print and a no-JS fallback;
    on screen the runtime hides `.lmr-anim` until it has applied the current frame
    (CSS `@media screen`), so this end state never flashes before playback. The
    world→viewport transform mirrors wanim's camera group but fits the frame into
    the viewport rect not the whole slide; each ``self.next()`` beat is a slide step."""
    from ..anim import constants as AC

    src = node.get("src")
    if not src:
        return pen
    from ..anim import set_default_color
    set_default_color(design.body)   # default text/shapes to the deck's foreground
    path = os.path.join(doc_dir, src)
    key = ("anim", path)
    if key not in _BUILD_MEMO:                  # run the module once per build
        try:
            _BUILD_MEMO[key] = _load_anim(path)
        except Exception as exc:                # a broken animation must not kill the deck
            _BUILD_MEMO[key] = exc
    ir = _BUILD_MEMO[key]
    if isinstance(ir, Exception):
        diag.warn(f"!anim {src} failed: {type(ir).__name__}: {ir}")
        return pen + 40.0
    global _ANIM_SEQ
    _ANIM_SEQ += 1                              # fresh ids for this placement
    aspect = float(getattr(AC, "ASPECT_RATIO", 16 / 9))
    fw, fh0 = float(getattr(AC, "FRAME_WIDTH", 14.222)), float(getattr(AC, "FRAME_HEIGHT", 8.0))

    vx, vy, vw, vh = _anim_viewport(node, design, pen, region, aspect, rbottom)

    # World→viewport: the camera group's matrix (like wanim's applyCamera), but
    # `s` fits the camera frame into the viewport rect (meet) rather than the
    # slide. `ppu` is the reference px/unit at the default frame height — strokes
    # are authored in px, so they divide by it (and by a node's own scale). Bake
    # the *last* camera state, matching the end frame below.
    cam = ir.get("camera") or []
    cv = cam[-1]["v"][-1] if cam else [0.0, 0.0, fh0]
    cx, cy, fh = float(cv[0]), float(cv[1]), float(cv[2] or fh0)
    ppu = min(vw / fw, vh / fh0)
    s = min(vw / (fh * aspect), vh / fh)
    ox, oy = vx + vw / 2 - s * cx, vy + vh / 2 + s * cy

    by: dict = {}
    for tr in ir.get("tracks", []):
        by.setdefault(tr["n"], {}).setdefault(tr["p"], []).append(tr)

    def final(props: dict, prop: str, st: dict):
        # End-state value: the last track's last keyframe, else the static baseline.
        trs = props.get(prop)
        return trs[-1]["v"][-1] if trs else st.get(prop)

    # A shared glyph outline is stored once in the anim's own <defs> (baked text /
    # maths reuse one <use>), id-namespaced so several anims/slides don't collide.
    dpfx = f"ad{_ANIM_SEQ}_"
    adefs = "".join(f'<path id="{dpfx}{k}" d="{v}"/>' for k, v in (ir.get("defs") or {}).items())

    # Each node becomes a `<use>` (glyph ref) or a `<path>` — the runtime updates
    # them by data-i. A collapsed draw-range emits no stroke at all, so a round
    # line-cap can't leave a stray dot (matters for any partially-drawn end state).
    # World shapes (3-D, projected by the player) are baked here with the final
    # camera of their view — the same maths as the runtime (lemur.anim.world).
    from lemur.anim import world as W

    wcams = []
    if ir.get("views"):
        _USES_WORLD[0] = True
    for v in ir.get("views") or []:
        ae = v["ae"][-1]["v"][-1] if v.get("ae") else v["ae0"]
        wcams.append(W.Camera(float(ae[0]), float(ae[1]), float(v["s"]), tuple(v["c"]), tuple(v["o"]), v["p"]))

    paths = []
    for n in ir.get("nodes", []):
        st = n.get("s", {})
        props = by.get(n["i"], {})
        tm = list(final(props, "t", st) or [1.0, 0.0, 0.0, 1.0, 0.0, 0.0])
        wcam = wcams[n["w"]] if "w" in n else None
        occ = (ir["views"][n["w"]].get("occ") or None) if wcam else None
        hidden, dim, length = False, 1.0, float(n.get("len") or 1.0)
        if wcam is not None:
            g3 = final(props, "g3", st)
            if g3 is not None and W.occludes(occ, wcam, g3):
                dim = float(n.get("ga", 0.3))
            if n.get("wk") == "anchor":
                a3 = final(props, "a3", st)
                if a3 is not None:
                    if W.occludes(occ, wcam, a3):
                        hidden = n.get("wr") == "hide"
                        dim *= float(n.get("ga", 0.3)) if n.get("wr") == "ghost" else 1.0
                    pa = W.project(wcam, a3)
                    tm[4] += float(pa[0])
                    tm[5] += float(pa[1])
            if n.get("wr") == "cull" and not float(np.asarray(n["nrm"]) @ W.toward(wcam)) > 0.0:
                hidden = True
        scale = (tm[0] ** 2 + tm[1] ** 2) ** 0.5 or 1.0
        a = [f'data-i="{n["i"]}"', f'transform="matrix({",".join(fmt(x) for x in tm)})"']
        if n.get("k") == "use":
            tag, geom = "use", f'href="#{dpfx}{n.get("ref", "")}"'
        elif n.get("k") == "w":
            tag = "path"
            p3 = final(props, "p3", st) or []
            struct = n.get("struct") or [[], []]
            flat, counts, cls, off = [], [], [], 0
            polys = []
            for c, cl in zip(struct[0], struct[1]):
                polys.append(np.asarray(p3[3 * off:3 * (off + c)], dtype=float).reshape(-1, 3))
                off += c
            baked = W.bake_paths(n.get("wk"), n.get("wr"), occ, wcam, polys, [bool(c) for c in struct[1]])
            length = 0.0
            for P2, cl in baked:
                flat.extend(float(x) for x in np.ravel(P2))
                counts.append(len(P2))
                cls.append(int(cl))
                seg = np.diff(np.vstack([P2, P2[:1]]) if cl else P2, axis=0)
                length += float(np.sum(np.hypot(seg[:, 0], seg[:, 1])))
            if not counts:
                hidden = True
            geom = f'd="{_flat_path(flat, [counts, cls, 1])}"'
        else:
            tag = "path"
            dtrs = props.get("d")   # a Transform morph → bake the end shape
            dstr = _flat_path(dtrs[-1]["v"][-1], dtrs[-1]["struct"]) if dtrs else n.get("d", "")
            geom = f'd="{dstr}"'
        a.append(geom)
        vis = final(props, "v", st)
        if (vis and vis[0] < 0.5) or hidden:
            a.append('style="display:none"')
        fo, fc = final(props, "fo", st), final(props, "fc", st)
        if dim < 1.0:
            fo = fo and [fo[0] * dim]
        if fo and fo[0] > 0.001:
            a.append(f'fill="{_rgb_hex(fc)}"')
            if fo[0] < 0.999:
                a.append(f'fill-opacity="{fmt(fo[0])}"')
        else:
            a.append('fill="none"')
        dr = final(props, "dr", st)
        drawn = (dr[1] - dr[0]) if dr else 1.0
        so, sw, sc = final(props, "so", st), final(props, "sw", st), final(props, "sc", st)
        if dim < 1.0:
            so = so and [so[0] * dim]
        if so and sw and so[0] > 0.001 and sw[0] > 1e-4 and drawn > 1e-4:
            a.append(f'stroke="{_rgb_hex(sc)}" stroke-width="{fmt(sw[0] / ppu / scale)}" '
                     f'stroke-linecap="round" stroke-linejoin="round"')
            if so[0] < 0.999:
                a.append(f'stroke-opacity="{fmt(so[0])}"')
            if n.get("dash") and drawn >= 0.9999:
                a.append(f'stroke-dasharray="{" ".join(fmt(x / (scale or 1.0)) for x in n["dash"])}"')
            if drawn < 0.9999:
                length = length or 1.0
                a.append(f'stroke-dasharray="{fmt(max(0.0, drawn) * length)} {fmt(length + 1)}" '
                         f'stroke-dashoffset="{fmt(-dr[0] * length)}"')
        else:
            a.append('stroke="none"')
        if n.get("rule"):
            a.append(f'fill-rule="{n["rule"]}"')
        paths.append((n.get("clip"), f'<{tag} {" ".join(a)}/>'))

    # A node may be clipped to a region (an inset). Emit one <clipPath> per region
    # (world coords, referenced inside anim-cam) and wrap runs of same-clip nodes in
    # a transform-less <g clip-path> so the clip stays in world space.
    clips: dict = {}
    for cl, _ in paths:
        if cl and tuple(cl) not in clips:
            clips[tuple(cl)] = f"{dpfx}clip{len(clips)}"
    adefs += "".join(
        f'<clipPath id="{cid2}" clipPathUnits="userSpaceOnUse">'
        f'<rect x="{fmt(k[0])}" y="{fmt(k[1])}" width="{fmt(k[2])}" height="{fmt(k[3])}"/></clipPath>'
        for k, cid2 in clips.items())
    body, cur_clip, buf = [], None, []
    for cl, ps in paths:
        key = tuple(cl) if cl else None
        if key != cur_clip:
            if buf:
                inner = "".join(buf)
                body.append(f'<g clip-path="url(#{clips[cur_clip]})">{inner}</g>' if cur_clip else inner)
            buf, cur_clip = [], key
        buf.append(ps)
    if buf:
        inner = "".join(buf)
        body.append(f'<g clip-path="url(#{clips[cur_clip]})">{inner}</g>' if cur_clip else inner)
    paths_svg = "".join(body)

    payload = json.dumps({
        "nodes": ir.get("nodes", []),
        "tracks": ir.get("tracks", []),
        "camera": cam,
        **({"views": ir["views"]} if ir.get("views") else {}),
        "beats": [b["t"] for b in ir.get("beats", [])],
        "duration": ir.get("duration", 0.0),
        "vp": [round(vx, 3), round(vy, 3), round(vw, 3), round(vh, 3)],
        "ppu": round(ppu, 5), "asp": aspect, "fh0": fh0,
    }, separators=(",", ":"))

    cid = f"vp{_ANIM_SEQ}"
    group = (
        f'<g class="lmr-anim" data-anim=\'{payload}\'>'
        f'<defs>{adefs}</defs>'
        f'<clipPath id="{cid}"><rect x="{fmt(vx)}" y="{fmt(vy)}" '
        f'width="{fmt(vw)}" height="{fmt(vh)}"/></clipPath>'
        f'<g clip-path="url(#{cid})">'
        f'<g class="anim-cam" transform="matrix({fmt(s)},0,0,{fmt(-s)},{fmt(ox)},{fmt(oy)})">'
        f'{paths_svg}</g></g></g>'
    )
    # Always on: the animation plays over its own beats (slide steps), it is not
    # a reveal that a gate hides. Beats are folded into the slide's step count by
    # the runtime, which reads `data-anim`.
    slide.add_overlay(group, 0, None)
    if (node.get("viewport") or "body").strip() != "body":
        return None                  # full / explicit rect: an overlay, it takes no flow space
    return vy + vh




# --------------------------------------------------------------------------
# slide templates — a template is a plain `render(ctx)` function registered under
# a name (a slide *kind*: cover/section/content, or your own). It draws onto
# `ctx.slide` with the free helpers below (`line`, `flow`, `footer`, …), reading
# the resolved design off `ctx.design`. Users register their own with
# @register("name") in a style.py, selected via `!slide[.name]`.
# --------------------------------------------------------------------------


@dataclass
class Ctx:
    """Everything a template's ``render(ctx)`` needs to draw one slide: the target
    ``slide``, the resolved ``design`` (+ its once-resolved ``serif``/``mono``/
    ``text_style``), and the slide's content and metadata."""
    slide: object          # the Slide to draw onto
    design: Design         # the resolved design box
    serif: str             # resolved body/serif family (Pango)
    mono: str              # resolved monospace family (Pango)
    text_style: TextStyle  # the inline text style for flowed body text
    title: str
    blocks: list
    role: str
    meta: dict
    doc_dir: str
    number: int = 1        # the slide number shown in the footer (the cover is 0)
    total: int = 1         # the number of numbered slides
    pres: dict = field(default_factory=dict)   # deck chrome: header/footer/logo/titleImage/…
    mods: frozenset = frozenset()              # variant modifiers: center/middle/plain/dark/fill
    show_number: bool = True                   # !slidenumbers off → False
    title_inline: list = field(default_factory=list)   # the title as inline nodes (maths, emphasis)
    bib: dict = field(default_factory=dict)    # citation key → number (deck-wide)


_TEMPLATES: dict = {}


def register(name: str):
    """Decorator: register a template — a ``render(ctx)`` function — under ``name``
    so a slide's role (`cover`/`section`/`content`) or a `!slide[.name]` variant
    can select it. Re-registering a built-in name restyles every slide of that
    kind."""
    def deco(fn):
        _TEMPLATES[name] = fn
        return fn
    return deco


def ctx_fonts(design: Design):
    """Resolve the design's font families once (Pango) and build the inline text
    style — the per-build render state that ``Ctx`` carries."""
    serif = pango.resolve_family(list(design.serif))
    mono = pango.resolve_family(list(design.mono))
    ts = TextStyle(font=serif, mono=mono, color=design.body, code_color=design.code,
                   link_color=design.accent, code_panel=design.code_bg, accent=design.accent)
    return serif, mono, ts


def _fx(ctx: Ctx) -> _Fx:
    """The flow context for a template context (built once per slide)."""
    fx = getattr(ctx, "_fx_cache", None)
    if fx is None or fx.slide is not ctx.slide:
        fx = _Fx(ctx.slide, ctx.design, ctx.text_style, ctx.mono, ctx.doc_dir,
                 math_scale_for(ctx.serif), ctx.bib)
        object.__setattr__(ctx, "_fx_cache", fx)
    return fx


# -- template helpers: free functions over Ctx (imported by user style.py) -----

def region(ctx: Ctx, name: str):
    """Named region as ``(x, w, y, h)`` — ``"title"`` or ``"body"``."""
    r = ctx.design.title_region if name == "title" else ctx.design.body_region
    return (r.x, r.w, r.y, r.h)


def line(ctx: Ctx, text, fs, top, region, color, weight="normal", align="left") -> float:
    """Place one (optionally centred, wrapping) text line — a string, or inline
    nodes (maths, emphasis) — with its first baseline one font ascent below
    ``top``; returns its height."""
    if not text:
        return 0.0
    st = ctx.text_style.derive(color=color, weight=weight)
    laid = layout_block(_as_inline(text), st, region[1] / fs, LH_BLOCK, align, math_scale_for(ctx.serif))
    if not laid.pieces:
        return 0.0
    return _emit_block(ctx.slide, laid.pieces, fs, top, region, align=align,
                       ascent=pango.font_metrics(ctx.serif, weight)[0])


def flow(ctx: Ctx, blocks, region, pen, gate=(0, None), align="left", rbottom=None,
         middle=None) -> float:
    """Flow ``blocks`` into ``region`` = ``(x, w)`` from ``pen`` (the first block
    starts right there) and draw their connectors; returns the bottom. Given the
    region's bottom (``rbottom``), a ``.middle`` slide (or ``middle=True``) is
    centred vertically between ``pen`` and it, and a ``!gap fill`` pushes down."""
    fx = _fx(ctx)
    g = _as_gate(gate)
    if middle is None:
        middle = "middle" in ctx.mods
    flex = rbottom is not None and (_has_fill(blocks) or middle)
    if middle and rbottom is not None:
        h, trail = _measure(fx, blocks, region[0], region[1], align, collapse=False)
        pen = max(pen, pen + (rbottom - pen - (h + trail)) / 2)
    bottom, trail = _flow_blocks(fx, blocks, region[0], region[1], pen, g, align, rbottom,
                                 first_zero=True, collapse=not flex)
    _draw_arrows(fx, blocks)
    return bottom


def _chrome_text(ctx: Ctx, nodes, fs: float, x: float, w: float, top: float, color: str,
                 align: str = "left") -> float:
    st = ctx.text_style.derive(color=color)
    return _text_block(_fx(ctx), nodes, st, fs, x, w, top, ALWAYS, align, LH_BLOCK)


def header(ctx: Ctx) -> None:
    """The deck header (`!header`): 0.5em, muted, at the top of the padding zone
    over a 1px rule."""
    hdr = (ctx.pres or {}).get("header")
    if not hdr:
        return
    d, br = ctx.design, ctx.design.body_region
    fs = 0.5 * d.body_size
    top = 0.42 * _pad_y(d)
    bottom = _chrome_text(ctx, hdr, fs, br.x, br.w, top, d.caption)
    ctx.slide.add_rect(br.x, bottom + 0.35 * fs, br.w, 1.0, d.rule)


def logo(ctx: Ctx) -> None:
    """The deck logo (`!logo`), top-right, 56px high (at most 30% wide)."""
    path = (ctx.pres or {}).get("logo")
    if not path:
        return
    p = os.path.join(ctx.doc_dir, path)
    href = _image_href(p)
    if href is None:
        diag.warn(f"logo not found: {path}")
        return
    size = _image_size(p)
    ar = size[0] / size[1] if (size and size[1]) else 3.0
    h = 56.0
    w = min(h * ar, ctx.design.width * 0.3)
    h = w / ar
    ctx.slide.add_image(ctx.design.width - ctx.design.body_region.x - w, 0.30 * _pad_y(ctx.design), w, h, href)


def footer(ctx: Ctx) -> None:
    """The deck footer: a 1px rule, the `!footer` text (or the deck title) left
    and ``n / total`` right, at 0.5em in the muted colour."""
    ft = (ctx.pres or {}).get("footer")
    nodes = _as_inline(ft) if ft else _as_inline((ctx.meta or {}).get("title", ""))
    show_num = ctx.show_number and ctx.total > 0 and ctx.number > 0
    if not nodes and not show_num:
        return
    d, br = ctx.design, ctx.design.body_region
    fs = 0.5 * d.body_size
    bottom = d.height - 0.42 * _pad_y(d)
    top = bottom - LH_BLOCK * fs - 0.35 * fs - 1.0
    ctx.slide.add_rect(br.x, top, br.w, 1.0, d.rule)
    ty = top + 1.0 + 0.35 * fs
    num_w = 0.0
    if show_num:
        num = [{"type": "text", "value": f"{ctx.number} / {ctx.total}"}]
        _chrome_text(ctx, num, fs, br.x, br.w, ty, d.caption, align="right")
        num_w = layout_block(num, ctx.text_style, 1e6).width * fs + fs
    if nodes:
        _chrome_text(ctx, nodes, fs, br.x, br.w - num_w, ty, d.caption)


def _pad_y(d: Design) -> float:
    return d.title_region.y


def body_bottom(ctx: Ctx) -> float:
    """The y of the body region's bottom (for a `!gap fill` / vertical centring)."""
    br = ctx.design.body_region
    return br.y + (br.h if br.h is not None else (ctx.design.height - br.y - 72.0))


def _check_overflow(ctx: Ctx, bottom: float, limit: float) -> None:
    if bottom > limit + 2.0:
        diag.warn(f"content overflows the slide body by {bottom - limit:.0f}px")


# -- built-in templates: render(ctx) functions --------------------------------

@register("content")
def content(ctx: Ctx) -> None:
    """A regular slide: title (left, with the accent rule), then the body flowed
    below it, with the margins between blocks collapsing. Variant modifiers:
    ``.plain`` (no chrome), ``.center`` (centre the body text), ``.middle``
    (vertically centre the body between title and footer), ``.fill`` (no
    padding). The title stays put under ``.center``/``.middle``."""
    d = ctx.design
    fx = _fx(ctx)
    tr, br = d.title_region, d.body_region
    plain, center, middle = "plain" in ctx.mods, "center" in ctx.mods, "middle" in ctx.mods
    align = "center" if center else "left"
    if "fill" in ctx.mods:
        tr = Region(0.0, 0.0, float(d.width), None)
        br = Region(0.0, 0.0, float(d.width), float(d.height))
    if not plain:
        header(ctx)
        logo(ctx)
    ts = d.title_size
    title = ctx.title_inline or _as_inline(ctx.title)
    body_top, lead = tr.y, 0.0
    if title:
        tst = ctx.text_style.derive(weight=int(d.title_weight), color=d.title,
                                    letter_spacing=d.title_spacing)
        bottom = _text_block(fx, title, tst, ts, tr.x, tr.w, tr.y, ALWAYS, "left", LH_BLOCK)
        rule_y = bottom + 0.15 * ts
        if d.title_rule > 0:
            ctx.slide.add_rect(tr.x, rule_y, tr.w, d.title_rule, d.accent)
        body_top, lead = rule_y + max(d.title_rule, 0.0), 0.6 * ts
    first_zero = False
    # an explicit body region (lower than where the body of a one-line title
    # would start — e.g. to clear a header bar) is a floor for the body
    natural = tr.y + LH_BLOCK * ts + 0.15 * ts + max(d.title_rule, 0.0)
    if br.y > natural + 1.0 and br.y > body_top + lead:
        body_top, lead, first_zero = br.y, 0.0, True
    rbottom = br.y + br.h if br.h is not None else body_bottom(ctx)
    if "fill" in ctx.mods:
        rbottom = float(d.height)
    blocks = ctx.blocks
    x, w = br.x, br.w
    if middle:
        h, trail = _measure(fx, blocks, x, w, align, collapse=False, first_zero=first_zero)
        start = body_top + lead
        # centred like `justify-content: center` — content taller than the body
        # overflows both ways: up into the title's margin and its own first
        # margin, but its first line never rises above the title rule
        items = [b for b in blocks if b.get("type") not in _SKIP]
        first_mt = 0.0
        if items:
            ot, it, _ob, _ib = _margins(fx, items[0])
            first_mt = _eff_margin(ot, it, bool(items[0].get("reveal")), False, True)
        start = max(body_top - first_mt, start + (rbottom - start - (h + trail)) / 2)
        bottom, _ = _flow_blocks(fx, blocks, x, w, start, ALWAYS, align, rbottom,
                                 first_zero=first_zero, collapse=False)
    else:
        flex = _has_fill(blocks)
        bottom, _ = _flow_blocks(fx, blocks, x, w, body_top, ALWAYS, align, rbottom,
                                 lead=lead, first_zero=first_zero, collapse=not flex)
    _draw_arrows(fx, blocks)
    _check_overflow(ctx, bottom, rbottom)
    if not plain:
        footer(ctx)


@register("section")
def section(ctx: Ctx) -> None:
    """A section divider (`#`): the title at 1.9em in the accent colour, centred
    with any content that follows it (centred text) in the middle of the slide;
    the footer stays, the header/logo go."""
    d = ctx.design
    fx = _fx(ctx)
    F = d.body_size
    size = 1.9 * F
    pad_x, pad_y = d.body_region.x, _pad_y(d)
    x, w = pad_x, d.width - 2 * pad_x
    title = ctx.title_inline or _as_inline(ctx.title)
    tst = ctx.text_style.derive(weight=int(d.title_weight), color=d.accent,
                                letter_spacing=d.title_spacing)
    laid = layout_block(title, tst, w / size, LH_BLOCK, "center", fx.math_scale)
    th = laid.height * size if laid.pieces else 0.0
    gap = 0.6 * size if laid.pieces else 0.0      # the h1's bottom margin is centred with it
    bh = 0.0
    if ctx.blocks:
        h, trail = _measure(fx, ctx.blocks, x, w, "center", first_zero=False)
        bh = h + trail
    total = th + gap + bh
    avail_top, avail_bottom = pad_y, d.height - pad_y
    y = avail_top + max(0.0, (avail_bottom - avail_top - total) / 2)
    if laid.pieces:
        y = _place(fx, laid, size, x, y, ALWAYS)
    if ctx.blocks:
        bottom, _ = _flow_blocks(fx, ctx.blocks, x, w, y + gap, ALWAYS, "center")
        _draw_arrows(fx, ctx.blocks)
        _check_overflow(ctx, bottom, avail_bottom)
    if "plain" not in ctx.mods:
        footer(ctx)


@register("cover")
def cover(ctx: Ctx) -> None:
    """The title slide, built from the deck metadata as a centred column: an
    optional `!titleimage` (≤390px high, ≤80% wide), the title (1.7em), the
    subtitle (0.85em, muted), and the byline — authors · affiliation · date
    (0.7em, muted). A theme may add a short accent rule and a small-caps byline."""
    d = ctx.design
    fx = _fx(ctx)
    F = d.body_size
    m = ctx.meta or {}
    pad_x, pad_y = d.body_region.x, _pad_y(d)
    x, w = pad_x, d.width - 2 * pad_x
    parts: list = []                            # (kind, payload, margin_top, margin_bottom)

    ti = (ctx.pres or {}).get("titleImage")
    if ti:
        p = os.path.join(ctx.doc_dir, ti)
        href = _image_href(p)
        if href is None:
            diag.warn(f"title image not found: {ti}")
        else:
            size = _image_size(p)
            ar = size[0] / size[1] if (size and size[1]) else 1.6
            iw = min(size[0] if size else w * 0.5, w * 0.8)
            ih = iw / ar
            if ih > 390.0:
                ih, iw = 390.0, 390.0 * ar
            parts.append(("image", (href, iw, ih), 0.0, 0.0))

    def text(nodes, fs, color, weight="normal", mt=0.0, mb=0.0, spacing=0.0):
        st = ctx.text_style.derive(color=color, weight=weight, letter_spacing=spacing)
        laid = layout_block(_as_inline(nodes), st, w / fs, LH_BLOCK if weight != "normal" else d.line_height,
                            "center", fx.math_scale)
        if laid.pieces:
            parts.append(("text", (laid, fs), mt, mb))

    tsz = d.cover_title_scale * F
    text(m.get("title", ""), tsz, d.title, weight=int(d.title_weight), mb=0.6 * tsz,
         spacing=d.title_spacing)
    if m.get("subtitle"):
        text(m["subtitle"], 0.85 * F, d.caption, mt=-0.2 * 0.85 * F, mb=0.85 * F)
    if d.cover_rule:
        parts.append(("rule", (w * 0.3,), 0.5 * F, 0.5 * F))
    byline = " · ".join([*(m.get("authors") or []), *(v for v in (m.get("affiliation"), m.get("date")) if v)])
    if byline:
        if d.cover_caps:
            text(byline.upper(), 0.55 * F, d.caption, mt=0.55 * F, mb=0.55 * F, spacing=0.08)
        else:
            text(byline, 0.7 * F, d.caption, mt=0.7 * F, mb=0.7 * F)

    def height(kind, payload):
        if kind == "image":
            return payload[2]
        if kind == "text":
            return payload[0].height * payload[1]
        return 2.0

    total = sum(mt + height(k, p) + mb for k, p, mt, mb in parts)
    y = pad_y + max(0.0, (d.height - 2 * pad_y - total) / 2)
    for kind, payload, mt, mb in parts:
        y += mt
        if kind == "image":
            href, iw, ih = payload
            ctx.slide.add_image((d.width - iw) / 2, y, iw, ih, href)
        elif kind == "text":
            laid, fs = payload
            _place(fx, laid, fs, x, y, ALWAYS)
        else:
            ctx.slide.add_rect((d.width - payload[0]) / 2, y, payload[0], 2.0, d.accent)
        y += height(kind, payload) + mb


#: Diagnostics of the last build (messages, in order).
LAST_WARNINGS: list = []


def load_style(path: str) -> "Design | None":
    """Import a deck's **style module** (`style.py`) — trusted Python that holds
    the whole design in one file. Importing it registers any `@register`ed
    templates (a side effect); its ``class Style`` (subclassing a shipped theme or
    the base) defines the design box, resolved to a :class:`Design`. Returns that,
    or ``None`` (no ``class Style`` — fall back to a theme/default while still
    using the registered templates)."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("_lmr_user_style", path)
    if not (spec and spec.loader):
        return None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)                       # runs @register decorators
    style_cls = getattr(mod, "Style", None)
    if not isinstance(style_cls, type):
        return None
    return resolve_design(style_cls, base_dir=os.path.dirname(os.path.abspath(path)))


def warn(msg: str) -> None:
    """A build diagnostic on stderr (the build carries on)."""
    LAST_WARNINGS.append(msg)
    print(f"lemur emit-svg: warning: {msg}", file=sys.stderr)


def resolve_theme(name: str, doc_dir: str) -> "Design | None":
    """A named theme → :class:`Design`: a shipped SVG theme, else a deck-local
    ``themes/<name>/`` (also ``$LEMUR_THEMES``) holding a ``style.py`` (preferred;
    importing it also registers its templates) or an HTML-emitter ``theme.css``
    (its ``--lmr-*`` tokens are mapped onto the design). None if not found."""
    if not name:
        return None
    if "/" not in name and os.sep not in name:
        d = theme_design(name)
        if d is not None:
            return d
    tdir = find_theme_dir(name, doc_dir)
    if tdir is None:
        return None
    sp = os.path.join(tdir, "style.py")
    if os.path.isfile(sp):
        d = load_style(sp)
        if d is not None:
            return d
    css = os.path.join(tdir, "theme.css")
    if os.path.isfile(css):
        return css_theme_design(css)
    return None


def _template_for(role: str, variant):
    """Pick the template's ``render`` function: a `!slide[.name]` variant wins,
    else the role, else `content`."""
    name = None
    if variant:
        for v in variant:
            if v in _TEMPLATES:
                name = v
                break
    if name is None:
        name = role if role in _TEMPLATES else "content"
    return _TEMPLATES[name]


def _split_variant(variant) -> tuple:
    """A `!slide[.a .b]` list → ``(template_name_or_None, [modifier_names])``. A
    name that is a registered template selects it; the rest are layout/chrome
    modifiers (``center``/``middle``/``plain``/``dark``)."""
    tname, mods = None, []
    for v in (variant or []):
        if v in _TEMPLATES and tname is None:
            tname = v
        else:
            mods.append(v)
    return tname, mods


def _apply_aspect(d: Design, aspect) -> Design:
    """C7: the deck's `!aspect` overrides the design box. Only 4:3 differs from the
    16:9 default; regions scale in x so they still fit the narrower box."""
    if aspect != "4:3" or d.width == 1440:
        return d
    sx = 1440.0 / d.width
    tr, br = d.title_region, d.body_region
    return replace(d, width=1440,
                   title_region=Region(tr.x * sx, tr.y, tr.w * sx, tr.h),
                   body_region=Region(br.x * sx, br.y, br.w * sx, br.h))


def _dark_design(d: Design) -> Design:
    """A dark per-slide variant (`.dark`): dark ground, light ink, accent kept."""
    return replace(d, bg="#14171c", title="#f2f5f8", body="#c4ccd6", math="#f2f5f8",
                   code="#dce3ec", code_bg="#0c0f14", caption="#8b98a5", rule="#39414c")


def wireframe_html(design: Design) -> str:
    """Render the design's regions as labelled, dashed boxes — a live-editable
    preview of the template (Plan-SVG §6)."""
    serif = pango.resolve_family(list(design.serif))
    slide = Slide(design.width, design.height, design.bg)
    palette = ["#6cb6ff", "#e0b070", "#3a7d44", "#c0392b", "#7a4b94", "#2e9c8e"]
    for i, (name, r) in enumerate((("title", design.title_region), ("body", design.body_region))):
        col = palette[i % len(palette)]
        h = r.h if r.h is not None else 130.0
        slide.add_overlay(
            f'<rect x="{fmt(r.x)}" y="{fmt(r.y)}" width="{fmt(r.w)}" height="{fmt(h)}" '
            f'fill="{col}" fill-opacity="0.07" stroke="{col}" stroke-width="3" stroke-dasharray="12 9"/>'
        )
        label = f"{name}  {int(r.w)}×{'auto' if r.h is None else int(r.h)}"
        shaped = pango.shape(label, font=serif, weight="bold")
        _emit_block(slide, _text_pieces(shaped, col), 30.0, r.y + 12, (r.x + 18, r.w - 36),
                    ascent=pango.font_metrics(serif, "bold")[0])
    return render_deck("master wireframe", [slide.to_svg(prefix="w")], design)


# --------------------------------------------------------------------------
# document -> single file
# --------------------------------------------------------------------------


def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


ASSETS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets")


def _read_asset(rel: str) -> str:
    with open(os.path.join(ASSETS_DIR, rel), encoding="utf-8") as fh:
        return fh.read()


# Live-reload client for the `--watch` dev server (never written to a built file).
_LIVE_RELOAD = (
    "<script>(function(){try{var es=new EventSource('/__lemur/events');"
    "es.addEventListener('reload',function(){location.reload();});"
    "es.addEventListener('error-report',function(){location.reload();});}catch(e){}})();</script>\n"
)


def render_deck(title: str, slide_svgs: list, design: Design, live_reload: bool = False,
                labels: "dict | None" = None, transition: "dict | None" = None,
                progress: "str | None" = None, design_w: int = 1920,
                bgs: "list | None" = None, defs: str = "") -> str:
    """Assemble the single HTML file: the slides' inline SVGs, the deck-wide
    outline store (``defs``: every glyph once, referenced from all slides), the
    runtime JS/CSS and its config."""
    css = _read_asset("svg/runtime.css")
    js = _read_asset("svg/runtime.js")
    if _USES_SHADERS[0]:                      # the live-shader player, only when needed
        js = _read_asset("svg/shader.js") + "\n" + js
    if _USES_WORLD[0]:                        # the 3-D projector for !anim world shapes
        js = _read_asset("svg/world.js") + "\n" + js
    tr = transition or {}
    cfg = {"labels": labels or {}, "across": tr.get("across") or "none",
           "step": tr.get("step") or "fade", "progress": progress}
    cfg_js = f"<script>window.LMR={json.dumps(cfg, separators=(',', ':'))};</script>\n"
    # Each slide carries its own background, so when the display aspect differs from
    # the design box the letterbox bars match the slide (seamless for full-bleed).
    bgs = bgs or [design.bg] * len(slide_svgs)
    shared = (f'<svg class="lmr-defs" width="0" height="0" aria-hidden="true" '
              f'style="position:absolute;width:0;height:0;overflow:hidden">'
              f'<defs>{defs}</defs></svg>\n') if defs else ""
    slides = "".join(f'<div class="slide" style="background:{bg}">{svg}</div>'
                     for svg, bg in zip(slide_svgs, bgs))
    head = (
        '<!doctype html>\n<html lang="en">\n<head>\n'
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>{_esc(title) or 'lemur deck'}</title>\n"
        f"<style>:root{{--bg:{design.bg};--fg:{design.body};--accent:{design.accent};--design-w:{design_w}px}}\n{css}</style>\n"
        "</head>\n<body>\n"
    )
    live = _LIVE_RELOAD if live_reload else ""
    # navigation wedges (bottom-right): dimmed at the deck ends, and the Next
    # wedge is cued in the accent colour when the current slide has more to reveal
    nav = ('<nav id="nav" aria-label="Slide navigation">'
           '<button type="button" class="nav-btn nav-prev" title="Previous (Left)">&#9664;</button>'
           '<button type="button" class="nav-btn nav-next" title="Next (Right)">&#9654;</button>'
           '</nav>')
    tail = f'\n{nav}\n{cfg_js}<script>{js}</script>\n{live}</body>\n</html>\n'
    return head + shared + slides + tail


def paginate(meta: dict, body: list) -> list:
    """Split the flat block list into slides on `pagebreak` markers. Each entry
    is ``(title, blocks, label_id, role, variant, title_inline)``; content before
    the first break becomes an initial slide titled from the deck metadata."""
    slides: list = []
    title_inline: list = []
    pbid = None
    blocks: list = []
    started = False
    role = "content"
    variant = None
    for node in body:
        if node.get("type") == "pagebreak":
            if started:
                slides.append((inline_text(title_inline), blocks, pbid, role, variant, title_inline))
            title_inline, pbid = list(node.get("title") or []), node.get("id")
            role, variant, blocks, started = node.get("role") or "content", node.get("variant"), [], True
        else:
            if not started:
                title_inline, started = _as_inline(meta.get("title", "")), True
            blocks.append(node)
    if started:
        slides.append((inline_text(title_inline), blocks, pbid, role, variant, title_inline))
    return slides


def _label_text(node: dict) -> str:
    return inline_text(node.get("title") or node.get("content") or node.get("caption")) or node.get("id", "")


def _walk_ids(obj, out: dict) -> None:
    if isinstance(obj, dict):
        if obj.get("id") and obj["id"] not in out:
            out[obj["id"]] = _label_text(obj)
        for v in obj.values():
            _walk_ids(v, out)
    elif isinstance(obj, list):
        for v in obj:
            _walk_ids(v, out)


def _collect_refs(slides: list) -> tuple:
    """``(labels {id: slide index}, texts {id: label text}, bib {key: number})``.
    A slide index is 1-based over the whole deck (the runtime's ``#/<n>``); a
    label's text is its target's title/content/caption, as the HTML deck showed."""
    labels: dict = {}
    texts: dict = {}
    bib: dict = {}
    n = 0
    for i, page in enumerate(slides, 1):
        title, blocks, pbid = page[0], page[1], page[2]
        if pbid:
            labels.setdefault(pbid, i)
            texts.setdefault(pbid, title or pbid)
        ids: dict = {}
        _walk_ids(blocks, ids)
        for k, txt in ids.items():
            labels.setdefault(k, i)
            texts.setdefault(k, txt)
        for node in _iter_type(blocks, "bibliography"):
            for e in node.get("entries", []):
                if e.get("key") not in bib:
                    n += 1
                    bib[e["key"]] = n
    return labels, texts, bib


def _iter_type(obj, typ):
    if isinstance(obj, dict):
        if obj.get("type") == typ:
            yield obj
        for v in obj.values():
            yield from _iter_type(v, typ)
    elif isinstance(obj, list):
        for v in obj:
            yield from _iter_type(v, typ)


def _resolve_refs(obj, labels: dict, texts: dict, bib: dict, problems: list) -> None:
    """Resolve `xref`/`cite` inline nodes in place: an xref gets its target's
    label ``text``; a citation its superscript ``text`` (``[1,2]``) and the keys
    that are ``missing``. Unresolved names are collected in ``problems``."""
    if isinstance(obj, list):
        for n in obj:
            _resolve_refs(n, labels, texts, bib, problems)
    elif isinstance(obj, dict):
        t = obj.get("type")
        if t == "xref":
            tgt = obj.get("target")
            if tgt in labels:
                obj["text"] = texts.get(tgt) or str(tgt)
            elif tgt in bib:                      # `@key` of a bib entry parsed as a ref
                obj["text"] = f"[{bib[tgt]}]"
            else:
                obj.pop("text", None)
                problems.append(f"unresolved reference @{tgt}")
        elif t == "cite":
            keys = obj.get("keys", [])
            known = [k for k in keys if k in bib]
            obj["text"] = "[" + ",".join(str(bib[k]) for k in known) + "]" if known else ""
            obj["missing"] = [k for k in keys if k not in bib]
            for k in obj["missing"]:
                problems.append(f"unresolved citation @{k}")
        for v in obj.values():
            if isinstance(v, (list, dict)):
                _resolve_refs(v, labels, texts, bib, problems)


def build_html(path: str, live_reload: bool = False, design: "Design | None" = None,
               style: "str | None" = None) -> tuple[str, tuple[int, int]]:
    """Parse ``path`` and return ``(html, (placements, distinct_outlines))``.

    The single source of truth for both the file build and the dev server.
    Design resolution: an explicit ``design`` > a **style.py** (``style`` path,
    else one next to the deck — it defines the design box *and* registers its
    templates) > the deck's ``!theme`` (shipped, or ``themes/<name>/`` next to
    the deck) > the default."""
    ast = deck_to_ast(Parser(load_lines(path)).parse())
    meta = ast.get("meta", {})
    pres = ast.get("presentation", {}) or {}   # deck chrome/transition/theme/aspect
    doc_dir = os.path.dirname(os.path.abspath(path))
    _saved_templates = dict(_TEMPLATES)        # this build's registrations must not leak
    _BUILD_MEMO.clear()
    _USES_SHADERS[0] = False
    _USES_WORLD[0] = False
    diag.drain()
    LAST_WARNINGS.clear()
    try:
        return _build_html(path, ast, meta, pres, doc_dir, live_reload, design, style)
    finally:
        _TEMPLATES.clear()
        _TEMPLATES.update(_saved_templates)
        _BUILD_MEMO.clear()




def _build_html(path, ast, meta, pres, doc_dir, live_reload, design, style):
    if design is None:   # explicit design wins; else a style.py; else !theme; else default
        sp = style or os.path.join(doc_dir, "style.py")   # explicit, else next to the deck
        if os.path.exists(sp):
            design = load_style(sp)                        # design box + registers templates
        if design is None and pres.get("theme"):
            design = resolve_theme(pres["theme"], doc_dir)
            if design is None:
                warn(f"theme {pres['theme']!r} not found (shipped: {', '.join(theme_names())}; "
                     f"or themes/{pres['theme']}/style.py|theme.css next to the deck) — using the default")
        if design is None:
            design = default_design()
    design = _apply_aspect(design, pres.get("aspect"))   # C7: !aspect overrides the design box
    dark = _dark_design(design)                            # for `.dark` slides
    latex.set_default_preamble(design.preamble_text())    # None -> packaged default

    pages = paginate(meta, ast.get("body", []))
    has_cover = bool(meta.get("title"))
    if has_cover:
        pages.insert(0, ("", [], None, "cover", None, []))  # synthesize a cover from the metadata
    labels, texts, bib = _collect_refs(pages)
    problems: list = []
    _resolve_refs(ast.get("body", []), labels, texts, bib, problems)
    for p in dict.fromkeys(problems):
        warn(p)

    # style.py registered its templates on import; resolve the fonts once per
    # design (light + dark, serving `.dark` slides).
    fonts = ctx_fonts(design)
    fonts_dark = ctx_fonts(dark)
    show_number = pres.get("slideNumbers") is not False
    numbered = len(pages) - (1 if has_cover else 0)

    defs = Defs("g")
    svgs, bgs, placements = [], [], 0
    for i, (title, blocks, _pbid, role, variant, title_inline) in enumerate(pages):
        tvar, mods = _split_variant(variant)              # D1: template name vs. modifiers
        d, (serif, mono, ts) = (dark, fonts_dark) if "dark" in mods else (design, fonts)
        slide = Slide(design.width, design.height, d.bg)
        render_fn = _template_for(role, [tvar] if tvar else None)
        try:
            render_fn(Ctx(slide=slide, design=d, serif=serif, mono=mono, text_style=ts,
                          title=title, blocks=blocks, role=role, meta=meta, doc_dir=doc_dir,
                          number=i if has_cover else i + 1, total=numbered, pres=pres,
                          mods=frozenset(mods), show_number=show_number,
                          title_inline=title_inline, bib=bib))
        except (latex.LatexError, pango.PangoUnavailable):
            raise
        except Exception as exc:  # a bug or a broken user template: report the slide, keep going
            import traceback
            diag.warn(f"rendering failed ({type(exc).__name__}: {exc}) — the slide is incomplete\n"
                      + "".join(traceback.format_exception(exc)[-3:]))
        for msg in diag.drain():
            label = f"slide {i + 1}" + (f" ({title[:50]!r})" if title else "")
            warn(f"{label}: {msg}")
        svgs.append(slide.to_svg(defs=defs))
        bgs.append(slide.bg)              # a template may have set a full-bleed bg
        placements += slide.stats()[0]

    prog = pres.get("progress")
    prog_pos = (prog.get("position") if isinstance(prog, dict) else "bottom") if prog else None
    transition = pres.get("transition") or design.transition   # deck !transition overrides the design default
    html = render_deck(meta.get("title", ""), svgs, design, live_reload=live_reload, labels=labels,
                       transition=transition, progress=prog_pos, design_w=design.width, bgs=bgs,
                       defs=defs.to_svg())
    return html, (placements, len(defs))


def build(path: str, outpath: str, design: "Design | None" = None, embed_images: bool = True,
          style: "str | None" = None) -> str:
    """Build the deck. ``embed_images=True`` writes one self-contained ``.html``;
    ``False`` treats ``outpath`` as a folder, copying images into ``images/`` and
    referencing them (like the browser emitter). ``style`` is an explicit
    ``style.py`` path (else one next to the deck is picked up automatically)."""
    global _IMG_SINK
    if embed_images:
        html, stats = build_html(path, design=design, style=style)
        with open(outpath, "w", encoding="utf-8") as fh:
            fh.write(html)
        build.last_stats = stats
        return outpath

    import shutil
    os.makedirs(os.path.join(outpath, "images"), exist_ok=True)
    seen: dict = {}

    def sink(p):
        if p not in seen:
            base, ext = os.path.splitext(os.path.basename(p))
            name, k = base + ext, 1
            while name in seen.values():             # same file name from another folder
                k += 1
                name = f"{base}-{k}{ext}"
            shutil.copy2(p, os.path.join(outpath, "images", name))
            seen[p] = name
        return f"images/{seen[p]}"

    _IMG_SINK = sink
    try:
        html, stats = build_html(path, design=design, style=style)
    finally:
        _IMG_SINK = None
    index = os.path.join(outpath, "index.html")
    with open(index, "w", encoding="utf-8") as fh:
        fh.write(html)
    build.last_stats = stats
    return index


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="emit a single self-contained SVG slide deck (.html) from a .lmr"
    )
    ap.add_argument("input", help="the .lmr document")
    ap.add_argument("-o", "--output", help="output .html (default: alongside input)")
    ap.add_argument("-s", "--style", help="a style.py file (design box + templates); "
                    "default: style.py next to the deck, if present")
    ap.add_argument("-t", "--theme", help=f"named theme: {', '.join(theme_names()) or 'clean'}, "
                    "or a themes/<name>/ folder next to the deck (a deck's !theme is used if "
                    "neither this nor --style is given)")
    ap.add_argument("-q", "--quality", choices=list(_QUALITY), default="medium",
                    help="emitted curve precision: draft/low (smaller, faster) … high/max "
                    "(print/deep-zoom). Output is vector, so on-screen the difference is subtle.")
    ap.add_argument("--wireframe", action="store_true",
                    help="render the resolved design's regions as labelled boxes")
    ap.add_argument("--separate-images", action="store_true",
                    help="write a folder with images copied to images/ instead of one embedded file")
    ap.add_argument("--strict", action="store_true",
                    help="exit with status 3 if the build reported any warning")
    ap.add_argument("-w", "--watch", action="store_true",
                    help="serve with live reload; rebuild on save")
    ap.add_argument("-p", "--port", type=int, default=8000, help="port for --watch (default 8000)")
    ap.add_argument("--no-open", action="store_true", help="don't open a browser for --watch")
    args = ap.parse_args(argv)

    try:
        set_precision(_QUALITY[args.quality])   # emitted curve precision
        style = args.style
        if style and not os.path.exists(style):
            print(f"lemur emit-svg: style file not found: {style}", file=sys.stderr)
            return 1
        if not args.input.endswith(".py") and not os.path.exists(args.input):
            print(f"lemur emit-svg: no such file: {args.input}", file=sys.stderr)
            return 1

        if args.wireframe:
            # render the regions of the resolved design (--theme, a style.py, or default)
            if args.theme:
                design = (resolve_theme(args.theme, os.path.dirname(os.path.abspath(args.input)))
                          or default_design())
            elif style or args.input.endswith(".py"):
                design = load_style(style or args.input) or default_design()
            else:
                cand = os.path.join(os.path.dirname(os.path.abspath(args.input)), "style.py")
                design = (load_style(cand) if os.path.exists(cand) else None) or default_design()
            out = args.output or (os.path.splitext(args.input)[0] + ".wireframe.html")
            with open(out, "w", encoding="utf-8") as fh:
                fh.write(wireframe_html(design))
            print(f"wrote {out}  (wireframe of 2 regions)")
            return 0

        # explicit --theme name > --style file / auto style.py > deck !theme > default
        if args.theme:
            design = resolve_theme(args.theme, os.path.dirname(os.path.abspath(args.input)))
            if design is None:
                print(f"lemur emit-svg: unknown theme {args.theme!r} "
                      f"(have: {', '.join(theme_names())}, or themes/<name>/ next to the deck)",
                      file=sys.stderr)
                return 1
        else:
            design = None

        if args.watch:
            from ..devserver import serve
            serve(args.input, port=args.port, open_browser=not args.no_open, design=design, style=style)
            return 0

        if args.separate_images:
            out = args.output or (os.path.splitext(args.input)[0] + "_deck")
            out = build(args.input, out, design=design, embed_images=False, style=style)
        else:
            out = args.output or (os.path.splitext(args.input)[0] + ".svg.html")
            build(args.input, out, design=design, style=style)
    except (latex.LatexError, pango.PangoUnavailable, LemurError) as exc:
        print(f"lemur emit-svg: {exc}", file=sys.stderr)
        return 1
    placements, distinct = getattr(build, "last_stats", (0, 0))
    nw = len(LAST_WARNINGS)
    print(f"wrote {out}  ({placements} placements, {distinct} distinct outlines"
          + (f", {nw} warning{'s' if nw != 1 else ''}" if nw else "") + ")")
    return 3 if (args.strict and nw) else 0


if __name__ == "__main__":
    sys.exit(main())
