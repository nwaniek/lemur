"""Drawing the audience's eye to something."""

from __future__ import annotations

import numpy as np

from .. import constants as C
from ..color import to_color
from ..mobject import Shape, VGroup, VShape
from .base import Animation, AnimationGroup, LaggedStart
from .creation import ShowPassingFlash
from .transform import Transform

__all__ = ["Indicate", "Flash", "Circumscribe", "Wiggle", "FocusOn", "Pulse", "ApplyWave"]


class Indicate(Animation):
    """Briefly swell and recolour -- the standard "look here"."""

    sampling = "dense"

    def __init__(self, mobject: Shape, scale: float = 1.2, color=C.YELLOW, **kwargs):
        kwargs.setdefault("rate_func", "there_and_back")
        super().__init__(mobject, **kwargs)
        self.scale_factor = scale
        self.color = to_color(color) if color is not None else None

    def begin(self) -> None:
        self.start = self.mobject.copy()
        self.target = self.mobject.copy()
        self.target.scale(self.scale_factor)
        if self.color is not None:
            self.target.set_color(self.color)
        self.center = self.mobject.get_center()
        super().begin()

    def interpolate(self, alpha: float) -> None:
        for cur, s, t in zip(self.mobject.family, self.start.family, self.target.family):
            cur.interpolate_from(s, t, alpha)


class Pulse(Indicate):
    """Swell without recolouring."""

    def __init__(self, mobject, scale: float = 1.15, **kwargs):
        super().__init__(mobject, scale=scale, color=None, **kwargs)


class Flash(Animation):
    """Radiating lines, like a spark."""

    sampling = "linear"

    def __init__(
        self,
        point,
        color=C.YELLOW,
        line_length: float = 0.25,
        n_lines: int = 12,
        radius: float = 0.35,
        stroke_width: float = 3.0,
        **kwargs,
    ):
        from ..shapes import Line

        kwargs.setdefault("run_time", 0.9)
        kwargs.setdefault("rate_func", "rush_from")
        origin = point.get_center() if isinstance(point, Shape) else np.asarray(point, dtype=float)
        lines = VGroup()
        for i in range(n_lines):
            a = i * C.TAU / n_lines
            u = np.array([np.cos(a), np.sin(a)])
            lines.add(Line(origin + u * radius, origin + u * (radius + line_length), color=color, stroke_width=stroke_width))
        super().__init__(lines, introducer=True, remover=True, **kwargs)
        self.origin = origin
        self.radius = radius
        self.line_length = line_length

    def begin(self) -> None:
        self.start = self.mobject.copy()
        super().begin()

    def interpolate(self, alpha: float) -> None:
        self.mobject.become(self.start)
        self.mobject.scale(0.4 + 1.0 * alpha, about_point=self.origin)
        for m in self.mobject.family:
            if isinstance(m, VShape):
                m.opacity_scale = float(np.clip(1.6 * (1 - alpha), 0, 1))


class Circumscribe(AnimationGroup):
    """Draw a box or circle around something, then rub it out."""

    def __init__(
        self,
        mobject: Shape,
        shape: str = "rect",
        color=C.YELLOW,
        buff: float = 0.12,
        stroke_width: float = 3.0,
        run_time: float = 1.2,
        fade_out: bool = True,
        **kwargs,
    ):
        from ..shapes import Circle, SurroundingRectangle

        if shape == "circle":
            frame = Circle.around(mobject, buff=buff, stroke_color=color, stroke_width=stroke_width)
        else:
            frame = SurroundingRectangle(mobject, buff=buff, stroke_color=color, stroke_width=stroke_width)
        self.frame = frame
        if fade_out:
            anims = [ShowPassingFlash(frame, width=0.55, run_time=run_time)]
        else:
            from .creation import Create

            anims = [Create(frame, run_time=run_time)]
        super().__init__(*anims, run_time=run_time, **kwargs)
        self.mobject = frame

    def mobjects(self):
        return [self.frame]

    def introduced(self):
        return [self.frame]

    def removed(self):
        return [self.frame]


class Wiggle(Animation):
    sampling = "dense"

    def __init__(self, mobject: Shape, scale: float = 1.08, angle: float = 0.06 * C.TAU, n: int = 6, **kwargs):
        kwargs.setdefault("rate_func", "linear")
        super().__init__(mobject, **kwargs)
        self.scale_factor = scale
        self.angle = angle
        self.n = n

    def begin(self) -> None:
        self.start = self.mobject.copy()
        self.center = self.mobject.get_center()
        super().begin()

    def interpolate(self, alpha: float) -> None:
        self.mobject.become(self.start)
        envelope = np.sin(np.pi * alpha)  # rise and fall
        self.mobject.scale(1 + (self.scale_factor - 1) * envelope, about_point=self.center)
        self.mobject.rotate(self.angle * envelope * np.sin(self.n * np.pi * alpha), about_point=self.center)


class FocusOn(Animation):
    """A shrinking spotlight that lands on a point."""

    sampling = "linear"

    def __init__(self, target, color=C.GREY, opacity: float = 0.2, **kwargs):
        from ..shapes import Circle

        kwargs.setdefault("run_time", 1.0)
        origin = target.get_center() if isinstance(target, Shape) else np.asarray(target, dtype=float)
        radius = 0.0 if not isinstance(target, Shape) else max(target.width, target.height) / 2 + 0.15
        spot = Circle(1.0, color=color, fill_color=color, fill_opacity=opacity, stroke_width=0.0).move_to(origin)
        super().__init__(spot, introducer=True, remover=True, **kwargs)
        self.origin = origin
        self.r0, self.r1 = C.FRAME_WIDTH / 2, max(radius, 0.12)
        self.opacity = opacity

    def begin(self) -> None:
        self.start = self.mobject.copy()
        super().begin()

    def interpolate(self, alpha: float) -> None:
        self.mobject.become(self.start)
        r = self.r0 + (self.r1 - self.r0) * alpha
        self.mobject.scale(r, about_point=self.origin)
        for m in self.mobject.family:
            if isinstance(m, VShape):
                m.opacity_scale = alpha


class ApplyWave(Animation):
    """Ripple a mobject along a direction."""

    sampling = "dense"

    def __init__(self, mobject: Shape, direction=C.UP, amplitude: float = 0.2, wavelength: float = 2.0, **kwargs):
        kwargs.setdefault("run_time", 1.2)
        kwargs.setdefault("rate_func", "linear")
        super().__init__(mobject, **kwargs)
        self.direction = np.asarray(direction, dtype=float)
        self.amplitude = amplitude
        self.wavelength = wavelength

    def begin(self) -> None:
        self.start = self.mobject.copy()
        lo, hi = self.mobject.get_bbox()
        self.x0, self.x1 = float(lo[0]), float(hi[0])
        super().begin()

    def interpolate(self, alpha: float) -> None:
        self.mobject.become(self.start)
        span = max(self.x1 - self.x0, 1e-6)
        envelope = np.sin(np.pi * alpha)  # no displacement at either end
        d = self.direction
        amp = self.amplitude * envelope

        def warp(pts: np.ndarray) -> np.ndarray:
            u = (pts[:, 0] - self.x0) / span
            phase = C.TAU * (u * span / self.wavelength - alpha * 2)
            return pts + np.outer(amp * np.sin(phase), d)

        self.mobject.apply_points_function(warp)
