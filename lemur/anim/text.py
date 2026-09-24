"""Text and maths mobjects.

Two engines, one representation:

* :class:`Text` / :class:`MarkupText` go through Pango (real shaping, kerning,
  ligatures, any installed font).
* :class:`Tex` / :class:`MathTex` go through LaTeX.

Both end up as outlines, so they morph, draw progressively, and need no fonts
or MathJax at display time.  Both are indexable: ``text[2]`` is the third
cluster, ``eq[0]`` the first symbol.
"""

from __future__ import annotations

from typing import Sequence

import numpy as np

from . import constants as C
from .color import to_color
from .mobject import GlyphRef, VGroup, VShape
from ..typeset import latex as _latex
from ..typeset import pango as _pango

__all__ = ["Text", "MarkupText", "Tex", "MathTex", "Title", "BulletList", "Paragraph", "set_text_defaults"]


_defaults = {
    "font": None,  # resolved lazily against what is installed
    "font_candidates": ["Fira Sans", "Source Sans Pro", "Inter", "Noto Sans", "DejaVu Sans", "sans"],
    "mono_candidates": ["Fira Mono", "JetBrains Mono", "DejaVu Sans Mono", "monospace"],
    "tex_preamble": _latex.default_preamble(),
    "color": C.WHITE,
}


def set_text_defaults(**kwargs) -> None:
    """Set process-wide text defaults (``font``, ``tex_preamble``, ``color``)."""
    _defaults.update(kwargs)


def default_font() -> str:
    if _defaults["font"] is None:
        _defaults["font"] = _pango.resolve_family(_defaults["font_candidates"])
    return _defaults["font"]


class _TextBase(VGroup):
    """Shared plumbing: build glyph submobjects, then place the block."""

    def _install(self, pieces: list[tuple[list[np.ndarray], list[bool], str, str | None]], em: float, color, opacity: float) -> None:
        base = to_color(color if color is not None else _defaults["color"])
        for subpaths, closed, key, own_color in pieces:
            glyph = VShape(
                fill_color=own_color if own_color else base,
                fill_opacity=opacity,
                stroke_width=0.0,
                stroke_color=own_color if own_color else base,
            )
            scaled = [np.asarray(sp, dtype=float) * em for sp in subpaths]
            glyph.set_subpaths(scaled, closed)
            if key:
                glyph.glyph = GlyphRef(key, [sp.copy() for sp in scaled], list(closed))
            self.add(glyph)

    def __getitem__(self, i):
        if isinstance(i, slice):
            return VGroup(*self.submobjects[i])
        return self.submobjects[i]

    def set_color_by_index(self, spec: dict) -> "_TextBase":
        """``{0: RED, slice(2, 5): BLUE}`` -> recolour those glyphs."""
        for k, col in spec.items():
            target = self[k]
            (target if isinstance(target, VGroup) else VGroup(target)).set_color(col)
        return self


# --------------------------------------------------------------------------
# Pango text
# --------------------------------------------------------------------------


class Text(_TextBase):
    """Shaped text in an installed font.

    ``Text("Hello", font_size=48, weight="bold")``.  Newlines are honoured;
    pass ``wrap_width`` (world units) to get automatic line breaking.
    """

    def __init__(
        self,
        text: str,
        font: str | None = None,
        font_size: float = C.DEFAULT_FONT_SIZE,
        weight: str | int = "normal",
        italic: bool = False,
        color=None,
        opacity: float = 1.0,
        line_spacing: float | None = None,
        align: str = "left",
        wrap_width: float | None = None,
        markup: bool = False,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.text = text
        self.font_size = font_size

        em = font_size / C.PIXELS_PER_UNIT
        shaped = _pango.shape(
            text,
            font=font or default_font(),
            weight=weight,
            italic=italic,
            line_spacing=line_spacing,
            align=align,
            wrap_width=(wrap_width / em) if wrap_width else None,
            markup=markup,
        )
        self._shaped = shaped
        self.line_height = shaped.line_height * em

        pieces = []
        self.chars: list[str] = []
        for cl in shaped.clusters:
            if not cl.subpaths:
                continue  # whitespace: no ink, no mobject
            pieces.append((cl.subpaths, cl.closed, _pango_key(cl), cl.color))
            self.chars.append(cl.text)
        self._install(pieces, em, color, opacity)
        self.center()

    def index_of(self, substring: str) -> int | None:
        """Index of the first glyph of ``substring`` (for recolouring)."""
        joined = "".join(self.chars)
        pos = joined.find(substring)
        return None if pos < 0 else pos

    def slice_of(self, substring: str) -> slice:
        i = self.index_of(substring)
        if i is None:
            return slice(0, 0)
        return slice(i, i + len(substring))


class MarkupText(Text):
    """Text with Pango markup: ``<b>``, ``<i>``, ``<span foreground='#f00'>``."""

    def __init__(self, text: str, **kwargs):
        kwargs["markup"] = True
        super().__init__(text, **kwargs)


class Paragraph(VGroup):
    """Several lines laid out as a block, each line its own mobject."""

    def __init__(self, *lines: str, line_buff: float = 0.25, align=C.LEFT, **kwargs):
        text_kwargs = {k: kwargs.pop(k) for k in list(kwargs) if k in _TEXT_KWARGS}
        super().__init__(**kwargs)
        for line in lines:
            self.add(Text(line, **text_kwargs))
        self.arrange(C.DOWN, buff=line_buff, aligned_edge=align)


_TEXT_KWARGS = {"font", "font_size", "weight", "italic", "color", "opacity", "line_spacing", "align", "wrap_width"}


class BulletList(VGroup):
    """A bulleted list; ``self.play(Reveal(items))`` reveals one at a time."""

    def __init__(
        self,
        *items: str,
        bullet: str = "•",
        buff: float = 0.42,
        indent: float = 0.42,
        levels: Sequence[int] | None = None,
        **kwargs,
    ):
        text_kwargs = {k: kwargs.pop(k) for k in list(kwargs) if k in _TEXT_KWARGS}
        super().__init__(**kwargs)
        levels = list(levels) if levels is not None else [0] * len(items)
        rows = []
        for item, level in zip(items, levels):
            mark = Text(bullet if level == 0 else "–", **text_kwargs)
            body = Text(item, **text_kwargs)
            body.next_to(mark, C.RIGHT, buff=0.28)
            row = VGroup(mark, body)
            row.shift(C.RIGHT * indent * level)
            rows.append(row)
            self.add(row)
        # Align on the bullets, not on the (variable-height) text bboxes.
        y = 0.0
        for row in rows:
            row.shift(np.array([0.0, y - row[0].get_center()[1]]))
            y -= buff
        self.center()
        self.items = rows


def _pango_key(cluster) -> str:
    return _latex.geometry_key(cluster.subpaths)


# --------------------------------------------------------------------------
# LaTeX
# --------------------------------------------------------------------------


class Tex(_TextBase):
    """LaTeX in text mode.  Pass several strings to make them individually
    addressable: ``Tex("The value ", "$x$", " is large")[1]``."""

    mode = "text"

    def __init__(
        self,
        *parts: str,
        font_size: float = C.DEFAULT_FONT_SIZE,
        color=None,
        opacity: float = 1.0,
        preamble: str | None = None,
        separator: str = "",
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.parts = parts
        self.font_size = font_size
        pre = preamble if preamble is not None else _defaults["tex_preamble"]

        body = _latex.wrap(separator.join(parts), self.mode)
        glyphs = _latex.tex_glyphs(body, pre)
        em = font_size / C.PIXELS_PER_UNIT

        self._install([(g.subpaths, g.closed, g.key, g.fill) for g in glyphs], em, color, opacity)
        self._group_by_parts(parts, pre, separator, len(glyphs))
        self.center()

    def _group_by_parts(self, parts, preamble, separator, total: int) -> None:
        """Nest glyphs under one submobject per argument, when the counts add up.

        Each part is typeset on its own purely to count its symbols; if the sum
        does not match the joined render (which happens when TeX merges things
        across the boundary), we keep the flat glyph list rather than guess.
        """
        if len(parts) < 2:
            return
        counts = []
        try:
            for p in parts:
                counts.append(len(_latex.tex_glyphs(_latex.wrap(p, self.mode), preamble)))
        except _latex.LatexError:
            return
        if sum(counts) != total:
            return
        glyphs = list(self.submobjects)
        self.submobjects = []
        i = 0
        for n in counts:
            self.add(VGroup(*glyphs[i : i + n]))
            i += n


class MathTex(Tex):
    """LaTeX in display maths mode: ``MathTex(r"e^{i\\pi} + 1 = 0")``."""

    mode = "display"


class Title(VGroup):
    """A slide title with an optional rule underneath."""

    def __init__(
        self,
        text: str,
        font_size: float = 54.0,
        weight: str = "semibold",
        underline: bool = True,
        color=None,
        rule_color=None,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.label = Text(text, font_size=font_size, weight=weight, color=color)
        self.add(self.label)
        if underline:
            from .shapes import Line

            w = max(self.label.width + 0.4, 2.0)
            rule = Line([-w / 2, 0], [w / 2, 0], stroke_width=2.5, color=rule_color or (color or C.WHITE))
            rule.set_stroke(opacity=0.35)
            rule.next_to(self.label, C.DOWN, buff=0.22)
            self.rule = rule
            self.add(rule)
        else:
            self.rule = None
