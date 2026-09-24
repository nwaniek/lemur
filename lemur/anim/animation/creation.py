"""Bringing things on and off the slide."""

from __future__ import annotations

import numpy as np

from .. import constants as C
from ..mobject import Shape, VGroup, VShape
from .base import Animation, AnimationGroup, LaggedStart

__all__ = [
    "Create",
    "Uncreate",
    "Write",
    "Unwrite",
    "DrawBorderThenFill",
    "FadeIn",
    "FadeOut",
    "GrowFromPoint",
    "GrowFromCenter",
    "GrowFromEdge",
    "GrowArrow",
    "SpinInFromNothing",
    "ShowPassingFlash",
    "Reveal",
    "AddTextLetterByLetter",
]


def _vparts(mobject: Shape) -> list[VShape]:
    return [m for m in mobject.family if isinstance(m, VShape) and m.has_points()]


class Create(Animation):
    """Draw a shape's outline progressively.

    Implemented by animating ``draw_range`` rather than rebuilding geometry,
    so the browser can do it with ``stroke-dashoffset`` -- smooth at any frame
    rate, and the path itself stays a single static element.
    """

    sampling = "linear"

    def __init__(self, mobject: Shape, lag_ratio: float = 0.0, reverse: bool = False, **kwargs):
        super().__init__(mobject, lag_ratio=lag_ratio, introducer=True, **kwargs)
        self.reverse = reverse

    def begin(self) -> None:
        self.parts = _vparts(self.mobject)
        self.fills = [m.fill_opacity for m in self.parts]
        for m in self.parts:
            m.draw_range = (0.0, 0.0)
            m.fill_opacity = 0.0
        super().begin()

    def interpolate(self, alpha: float) -> None:
        n = len(self.parts)
        for i, m in enumerate(self.parts):
            a = _staggered(alpha, i, n, self.lag_ratio)
            m.draw_range = (1.0 - a, 1.0) if self.reverse else (0.0, a)
            # Fill arrives over the second half, once there is a shape to fill.
            m.fill_opacity = self.fills[i] * float(np.clip(2 * a - 1, 0, 1))


class Uncreate(Create):
    """Rub a shape out again."""

    def __init__(self, mobject, **kwargs):
        kwargs.setdefault("rate_func", "smooth")
        super().__init__(mobject, **kwargs)
        self.remover = True
        self.introducer = False

    def interpolate(self, alpha: float) -> None:
        super().interpolate(1.0 - alpha)


class DrawBorderThenFill(Animation):
    """Trace the outline in one colour, then let the real fill bloom in."""

    sampling = "linear"

    def __init__(self, mobject: Shape, border_color=None, border_width: float = 3.0, **kwargs):
        kwargs.setdefault("run_time", 2.0)
        super().__init__(mobject, introducer=True, **kwargs)
        self.border_color = border_color
        self.border_width = border_width

    def begin(self) -> None:
        self.parts = _vparts(self.mobject)
        self.style = [(m.fill_opacity, m.stroke_width, m.stroke_color, m.stroke_opacity) for m in self.parts]
        for m in self.parts:
            m.draw_range = (0.0, 0.0)
            m.fill_opacity = 0.0
            m.stroke_width = self.border_width
            m.stroke_opacity = 1.0
            if self.border_color is not None:
                from ..color import to_color

                m.stroke_color = to_color(self.border_color)
        super().begin()

    def interpolate(self, alpha: float) -> None:
        draw = float(np.clip(alpha * 2, 0, 1))
        fill = float(np.clip(alpha * 2 - 1, 0, 1))
        for m, (f0, w0, c0, so0) in zip(self.parts, self.style):
            m.draw_range = (0.0, draw)
            m.fill_opacity = f0 * fill
            m.stroke_width = self.border_width + (w0 - self.border_width) * fill
            m.stroke_opacity = 1.0 + (so0 - 1.0) * fill
            if self.border_color is not None:
                from ..color import interpolate_color

                m.stroke_color = interpolate_color(self.border_color, c0, fill)


class _WholeGroup(AnimationGroup):
    """A group animation that the scene should treat as one mobject.

    Without this the scene would add each glyph individually and never add the
    text object itself.
    """

    def mobjects(self):
        return [self.mobject]

    def introduced(self):
        return [self.mobject] if self.introducer else []

    def removed(self):
        return [self.mobject] if self.remover else []


class Write(_WholeGroup):
    """Draw text (or any group) piece by piece, in reading order."""

    def __init__(self, mobject: Shape, lag_ratio: float | None = None, run_time: float | None = None, **kwargs):
        parts = list(mobject.submobjects) or [mobject]
        n = len(parts)
        if lag_ratio is None:
            # Enough overlap to read as one sweep, enough lag to see direction.
            lag_ratio = float(np.clip(3.5 / max(n, 1), 0.1, 0.6))
        if run_time is None:
            # Sub-linear in length: a long title should not crawl.
            run_time = float(np.clip(0.5 + 0.28 * np.sqrt(n), 0.8, 3.0))
        stroke = kwargs.pop("stroke_width", None)
        children = [_WriteOne(p, stroke_width=stroke) for p in parts]
        super().__init__(*children, lag_ratio=lag_ratio, run_time=run_time, **kwargs)
        self.mobject = mobject
        self.introducer = True


class _WriteOne(Animation):
    """Outline a glyph, then fill it -- the strokes of a pen."""

    sampling = "linear"

    def __init__(self, mobject: Shape, stroke_width: float | None = None, **kwargs):
        super().__init__(mobject, **kwargs)
        self.pen_width = stroke_width

    def begin(self) -> None:
        self.parts = _vparts(self.mobject)
        self.style = [(m.fill_opacity, m.stroke_width, m.stroke_opacity) for m in self.parts]
        for m in self.parts:
            m.draw_range = (0.0, 0.0)
            m.fill_opacity = 0.0
            # Text has no stroke of its own; borrow the fill colour for the pen.
            m.stroke_color = m.fill_color
            m.stroke_width = self.pen_width if self.pen_width is not None else 1.6
            m.stroke_opacity = 1.0
        super().begin()

    def interpolate(self, alpha: float) -> None:
        draw = float(np.clip(alpha / 0.7, 0, 1))
        fill = float(np.clip((alpha - 0.4) / 0.6, 0, 1))
        for m, (f0, w0, so0) in zip(self.parts, self.style):
            m.draw_range = (0.0, draw)
            m.fill_opacity = f0 * fill
            m.stroke_width = (self.pen_width if self.pen_width is not None else 1.6) * (1 - fill) + w0 * fill
            m.stroke_opacity = 1.0 * (1 - fill) + so0 * fill


class Unwrite(Write):
    def __init__(self, mobject, **kwargs):
        super().__init__(mobject, **kwargs)
        self.remover = True
        self.introducer = False

    def interpolate(self, alpha: float) -> None:
        super().interpolate(1.0 - alpha)


class FadeIn(Animation):
    sampling = "linear"

    def __init__(self, mobject: Shape, shift=None, scale: float | None = None, **kwargs):
        super().__init__(mobject, introducer=True, **kwargs)
        self.shift_vector = None if shift is None else np.asarray(shift, dtype=float)
        self.scale_factor = scale

    def begin(self) -> None:
        self.target = self.mobject.copy()
        self.start = self.mobject.copy()
        if self.shift_vector is not None:
            self.start.shift(-self.shift_vector)
        if self.scale_factor is not None:
            self.start.scale(self.scale_factor, about_point=self.mobject.get_center())
        for m in self.start.family:
            if isinstance(m, VShape):
                m.opacity_scale = 0.0
        super().begin()

    def interpolate(self, alpha: float) -> None:
        for cur, s, t in zip(self.mobject.family, self.start.family, self.target.family):
            cur.interpolate_from(s, t, alpha)


class FadeOut(FadeIn):
    def __init__(self, mobject, **kwargs):
        super().__init__(mobject, **kwargs)
        self.remover = True
        self.introducer = False

    def begin(self) -> None:
        super().begin()
        # Fading out is fading in, backwards.
        self.start, self.target = self.target, self.start
        if self.shift_vector is not None:
            self.target.shift(2 * self.shift_vector)


class GrowFromPoint(Animation):
    sampling = "linear"

    def __init__(self, mobject: Shape, point, **kwargs):
        super().__init__(mobject, introducer=True, **kwargs)
        self.point = np.asarray(point, dtype=float)

    def begin(self) -> None:
        self.target = self.mobject.copy()
        self.start = self.mobject.copy()
        self.start.scale(1e-6, about_point=self.point)
        self.start.move_to(self.point)
        for m in self.start.family:
            if isinstance(m, VShape):
                m.opacity_scale = 0.0
        super().begin()

    def interpolate(self, alpha: float) -> None:
        for cur, s, t in zip(self.mobject.family, self.start.family, self.target.family):
            cur.interpolate_from(s, t, alpha)


class GrowFromCenter(GrowFromPoint):
    def __init__(self, mobject, **kwargs):
        super().__init__(mobject, mobject.get_center(), **kwargs)


class GrowFromEdge(GrowFromPoint):
    def __init__(self, mobject, edge=C.DOWN, **kwargs):
        super().__init__(mobject, mobject.get_corner(edge), **kwargs)


class GrowArrow(GrowFromPoint):
    """Extend an arrow out of its own tail."""

    def __init__(self, arrow, **kwargs):
        start = arrow.get_start() if hasattr(arrow, "get_start") else arrow.get_center()
        super().__init__(arrow, start, **kwargs)


class SpinInFromNothing(Animation):
    sampling = "dense"

    def __init__(self, mobject: Shape, angle: float = C.PI / 2, **kwargs):
        super().__init__(mobject, introducer=True, **kwargs)
        self.angle = angle

    def begin(self) -> None:
        self.target = self.mobject.copy()
        self.center = self.mobject.get_center()
        super().begin()

    def interpolate(self, alpha: float) -> None:
        self.mobject.become(self.target)
        self.mobject.scale(max(alpha, 1e-6), about_point=self.center)
        self.mobject.rotate(self.angle * (alpha - 1), about_point=self.center)
        for m in self.mobject.family:
            if isinstance(m, VShape):
                m.opacity_scale *= alpha


class ShowPassingFlash(Animation):
    """A highlight that sweeps along a path and vanishes."""

    sampling = "linear"

    def __init__(self, mobject: VShape, width: float = 0.25, **kwargs):
        kwargs.setdefault("rate_func", "linear")
        super().__init__(mobject, introducer=True, remover=True, **kwargs)
        self.band = width

    def begin(self) -> None:
        self.parts = _vparts(self.mobject)
        super().begin()

    def interpolate(self, alpha: float) -> None:
        # The window runs off both ends so the flash enters and leaves cleanly.
        pos = alpha * (1 + self.band)
        for m in self.parts:
            m.draw_range = (max(0.0, pos - self.band), min(1.0, pos))


class Reveal(_WholeGroup):
    """Fade in a group's children one after another -- bullet points."""

    def __init__(self, mobject: Shape, shift=None, lag_ratio: float = 0.4, **kwargs):
        parts = list(mobject.submobjects) or [mobject]
        shift = C.RIGHT * 0.3 if shift is None else shift
        super().__init__(*[FadeIn(p, shift=shift) for p in parts], lag_ratio=lag_ratio, **kwargs)
        self.mobject = mobject
        self.introducer = True


class AddTextLetterByLetter(_WholeGroup):
    """Typewriter effect."""

    def __init__(self, text: Shape, time_per_char: float = 0.06, **kwargs):
        parts = list(text.submobjects) or [text]
        kwargs.setdefault("run_time", max(0.4, time_per_char * len(parts)))
        super().__init__(*[FadeIn(p, run_time=0.12) for p in parts], lag_ratio=1.0, **kwargs)
        self.mobject = text
        self.introducer = True


def _staggered(alpha: float, i: int, n: int, lag_ratio: float) -> float:
    """Per-part alpha when a single animation staggers its own pieces."""
    if n <= 1 or lag_ratio <= 0:
        return alpha
    span = 1.0 / (1 + lag_ratio * (n - 1))
    start = i * lag_ratio * span
    return float(np.clip((alpha - start) / span, 0.0, 1.0))
