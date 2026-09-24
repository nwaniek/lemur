"""Transforming one mobject into another, and moving things around."""

from __future__ import annotations

from typing import Callable

import numpy as np

from .. import constants as C
from ..mobject import Shape, VShape
from .base import Animation

__all__ = [
    "Transform",
    "ReplacementTransform",
    "TransformFromCopy",
    "ClockwiseTransform",
    "CounterclockwiseTransform",
    "FadeTransform",
    "Restore",
    "Rotate",
    "Rotating",
    "MoveAlongPath",
    "MoveTo",
    "Shift",
    "ScaleBy",
    "ApplyFunction",
    "AnimationBuilder",
    "align_families",
]


# --------------------------------------------------------------------------
# path functions
# --------------------------------------------------------------------------


def straight_path(a: np.ndarray, b: np.ndarray, alpha: float) -> np.ndarray:
    return a + (b - a) * alpha


def arc_path(arc_angle: float) -> Callable:
    """Points travel along a circular arc instead of a straight line."""

    def fn(a: np.ndarray, b: np.ndarray, alpha: float) -> np.ndarray:
        if abs(arc_angle) < 1e-9:
            return straight_path(a, b, alpha)
        mid = (a + b) / 2
        d = b - a
        perp = np.stack([-d[..., 1], d[..., 0]], axis=-1)
        centre = mid + perp / (2 * np.tan(arc_angle / 2))
        rel = a - centre
        th = arc_angle * alpha
        c, s = np.cos(th), np.sin(th)
        rot = np.stack([rel[..., 0] * c - rel[..., 1] * s, rel[..., 0] * s + rel[..., 1] * c], axis=-1)
        return centre + rot

    return fn


# --------------------------------------------------------------------------
# family alignment
# --------------------------------------------------------------------------


def _null_like(proto: Shape, at_center: np.ndarray) -> Shape:
    """An invisible, point-sized stand-in so families can be zipped up."""
    clone = proto.copy()
    clone.apply_points_function(lambda p: np.repeat(at_center[None, :], len(p), axis=0))
    for m in clone.family:
        if isinstance(m, VShape):
            m.opacity_scale = 0.0
    return clone


def align_families(a: Shape, b: Shape) -> None:
    """Give ``a`` and ``b`` identical tree shape and matching point counts.

    Missing children on either side are filled with zero-size invisible copies
    placed at that side's centre, so a shape that gains parts appears to grow
    them out of itself rather than fly in from the origin.
    """
    ca = a.get_center() if a.has_points() or a.submobjects else np.zeros(2)
    cb = b.get_center() if b.has_points() or b.submobjects else np.zeros(2)
    na, nb = len(a.submobjects), len(b.submobjects)
    for i in range(na, nb):
        a.submobjects.append(_null_like(b.submobjects[i], ca))
    for i in range(nb, na):
        b.submobjects.append(_null_like(a.submobjects[i], cb))
    for x, y in zip(a.submobjects, b.submobjects):
        align_families(x, y)
    if isinstance(a, VShape) and isinstance(b, VShape):
        a.align_points_with(b)


# --------------------------------------------------------------------------
# transform
# --------------------------------------------------------------------------


class Transform(Animation):
    """Morph ``mobject`` into ``target``, geometry and paint together."""

    def __init__(
        self,
        mobject: Shape,
        target: Shape,
        path_arc: float = 0.0,
        path_func: Callable | None = None,
        replace: bool = False,
        **kwargs,
    ):
        super().__init__(mobject, **kwargs)
        self.target_source = target
        self.path_func = path_func or (arc_path(path_arc) if path_arc else None)
        self.replace = replace
        # A plain morph is affine in alpha -- two keyframes reproduce it
        # exactly.  Curved paths are not, so those need real sampling.
        self.sampling = "dense" if self.path_func else "linear"

    def begin(self) -> None:
        self.target = self.target_source.copy()
        align_families(self.mobject, self.target)
        self.start = self.mobject.copy()
        super().begin()

    def interpolate(self, alpha: float) -> None:
        for cur, s, t in zip(self.mobject.family, self.start.family, self.target.family):
            _blend(cur, s, t, alpha, self.path_func)

    def clean_up(self, scene) -> None:
        if self.replace:
            scene.remove(self.mobject)
            scene.add(self.target_source)
            self.target_source.become(self.target)


def _blend(cur: Shape, s: Shape, t: Shape, alpha: float, path_func) -> None:
    if isinstance(cur, VShape) and isinstance(s, VShape) and isinstance(t, VShape):
        cur.interpolate_from(s, t, alpha, path_func)
    else:
        cur.interpolate_from(s, t, alpha)


class ReplacementTransform(Transform):
    """Like :class:`Transform`, but the *target* stays in the scene afterwards.

    Use this when you keep a reference to the target and want it to be the
    live object from then on.
    """

    def __init__(self, mobject, target, **kwargs):
        super().__init__(mobject, target, replace=True, **kwargs)


class TransformFromCopy(Transform):
    """Leave the original in place; a copy of it becomes the target."""

    def __init__(self, mobject, target, **kwargs):
        self.original = mobject
        super().__init__(mobject.copy(), target, replace=True, **kwargs)
        self.introducer = True


class ClockwiseTransform(Transform):
    def __init__(self, mobject, target, **kwargs):
        kwargs.setdefault("path_arc", -C.PI / 2)
        super().__init__(mobject, target, **kwargs)


class CounterclockwiseTransform(Transform):
    def __init__(self, mobject, target, **kwargs):
        kwargs.setdefault("path_arc", C.PI / 2)
        super().__init__(mobject, target, **kwargs)


class FadeTransform(Animation):
    """Cross-fade rather than morph -- better when the shapes are unrelated."""

    sampling = "linear"

    def __init__(self, mobject: Shape, target: Shape, **kwargs):
        super().__init__(mobject, **kwargs)
        self.target = target
        self.introducer = True

    def begin(self) -> None:
        self._from = _opacities(self.mobject)
        self._to = _opacities(self.target)
        self._start_a = self.mobject.copy()
        self._start_b = self.target.copy()
        self._center_a = self.mobject.get_center()
        self._center_b = self.target.get_center()
        super().begin()

    def interpolate(self, alpha: float) -> None:
        # Cross-fade, and drift both towards the other's position, so the swap
        # reads as one motion rather than two unrelated fades.
        self.mobject.become(self._start_a)
        self.target.become(self._start_b)
        self.mobject.shift((self._center_b - self._center_a) * alpha)
        self.target.shift((self._center_a - self._center_b) * (1 - alpha))
        _set_opacities(self.mobject, self._from, 1 - alpha)
        _set_opacities(self.target, self._to, alpha)

    def mobjects(self):
        return [self.mobject, self.target]

    def removed(self):
        return [self.mobject]

    def introduced(self):
        return [self.target]


def _opacities(mob: Shape) -> list[float]:
    return [m.opacity_scale for m in mob.family if isinstance(m, VShape)]


def _set_opacities(mob: Shape, base: list[float], factor: float) -> None:
    it = iter(base)
    for m in mob.family:
        if isinstance(m, VShape):
            m.opacity_scale = next(it, 1.0) * factor


class Restore(Transform):
    """Transform back to the state saved by ``mobject.save_state()``."""

    def __init__(self, mobject: Shape, **kwargs):
        saved = getattr(mobject, "_saved_state", None)
        if saved is None:
            raise ValueError("call mobject.save_state() before Restore(mobject)")
        super().__init__(mobject, saved, **kwargs)


# --------------------------------------------------------------------------
# motion
# --------------------------------------------------------------------------


class Rotate(Animation):
    """Spin in place (or about a point).  Sampled densely: a rotation is not
    linear in its point coordinates."""

    sampling = "dense"

    def __init__(self, mobject: Shape, angle: float = C.PI, about_point=None, about_edge=C.ORIGIN, **kwargs):
        super().__init__(mobject, **kwargs)
        self.angle = float(angle)
        self.about_point = about_point
        self.about_edge = about_edge

    def begin(self) -> None:
        self.start = self.mobject.copy()
        self.pivot = self.mobject._about(self.about_point, self.about_edge)
        super().begin()

    def interpolate(self, alpha: float) -> None:
        self.mobject.become(self.start)
        self.mobject.rotate(self.angle * alpha, about_point=self.pivot)


class Rotating(Rotate):
    def __init__(self, mobject, angle: float = C.TAU, run_time: float = 4.0, **kwargs):
        kwargs.setdefault("rate_func", "linear")
        super().__init__(mobject, angle, run_time=run_time, **kwargs)


class MoveAlongPath(Animation):
    """Slide a mobject along a path mobject (by arc length)."""

    sampling = "dense"

    def __init__(self, mobject: Shape, path: VShape, align: bool = False, **kwargs):
        super().__init__(mobject, **kwargs)
        self.path = path
        self.align = align

    def begin(self) -> None:
        self.start = self.mobject.copy()
        self._angle0 = 0.0
        super().begin()

    def interpolate(self, alpha: float) -> None:
        self.mobject.become(self.start)
        point = self.path.point_from_proportion(alpha)
        if self.align:
            eps = 1e-3
            ahead = self.path.point_from_proportion(min(1.0, alpha + eps))
            behind = self.path.point_from_proportion(max(0.0, alpha - eps))
            d = ahead - behind
            self.mobject.rotate(float(np.arctan2(d[1], d[0])), about_point=self.start.get_center())
        self.mobject.move_to(point)


class _MethodAnimation(Transform):
    """Base for the tiny convenience wrappers below."""

    def __init__(self, mobject, method: Callable, *args, **kwargs):
        anim_kwargs = {k: kwargs.pop(k) for k in list(kwargs) if k in _ANIM_KWARGS}
        target = mobject.copy()
        method(target, *args, **kwargs)
        super().__init__(mobject, target, **anim_kwargs)


_ANIM_KWARGS = {"run_time", "rate_func", "lag_ratio", "path_arc", "path_func", "name"}


class MoveTo(_MethodAnimation):
    def __init__(self, mobject, point, **kwargs):
        super().__init__(mobject, Shape.move_to, point, **kwargs)


class Shift(_MethodAnimation):
    def __init__(self, mobject, vector, **kwargs):
        super().__init__(mobject, Shape.shift, vector, **kwargs)


class ScaleBy(_MethodAnimation):
    def __init__(self, mobject, factor, **kwargs):
        super().__init__(mobject, Shape.scale, factor, **kwargs)


class ApplyFunction(_MethodAnimation):
    """Warp a mobject through an arbitrary point map."""

    sampling = "dense"

    def __init__(self, mobject, function, **kwargs):
        super().__init__(mobject, Shape.apply_function, function, **kwargs)


# --------------------------------------------------------------------------
# .animate
# --------------------------------------------------------------------------


class AnimationBuilder:
    """Implements ``mobject.animate.shift(UP).set_color(RED)``.

    Method calls are replayed on a copy; playing the builder morphs the
    original into that copy.  ``mobject.animate(run_time=2)`` sets options.
    """

    def __init__(self, mobject: Shape):
        self.mobject = mobject
        self.target = mobject.copy()
        self.options: dict = {}
        self._calls: list[str] = []

    def __call__(self, **options) -> "AnimationBuilder":
        self.options.update(options)
        return self

    def __getattr__(self, name: str):
        if name.startswith("_"):
            raise AttributeError(name)
        attr = getattr(self.target, name, None)
        if attr is None:
            raise AttributeError(f"{type(self.mobject).__name__} has no method {name!r}")
        if not callable(attr):
            return attr

        def wrapper(*args, **kwargs):
            attr(*args, **kwargs)
            self._calls.append(name)
            return self

        return wrapper

    def build(self) -> Transform:
        if not self._calls:
            raise ValueError("`.animate` was used without calling any method")
        anim = Transform(self.mobject, self.target, **self.options)
        anim.name = "animate." + ".".join(self._calls)
        return anim

    def __repr__(self) -> str:
        return f"<animate {self.mobject!r} {'.'.join(self._calls)}>"
