"""Animation base classes.

An :class:`Animation` is a function of ``alpha in [0, 1]`` that mutates its
mobject.  The scene never renders frames itself: it *samples* animations at a
series of alphas and records the resulting states, which become keyframes in
the output.  Everything else in lemur.anim follows from that.
"""

from __future__ import annotations

from typing import Callable, Iterable, Sequence

import numpy as np

from .. import rate as rate_module
from ..mobject import Shape

__all__ = ["Animation", "AnimationGroup", "Succession", "LaggedStart", "Wait", "prepare"]


class Animation:
    """Base class.  Subclasses implement :meth:`interpolate`."""

    #: How finely the scene should sample this animation.  "linear" means the
    #: state is affine in alpha, so two keyframes reproduce it exactly.
    sampling = "normal"  # "linear" | "normal" | "dense"

    def __init__(
        self,
        mobject: Shape | None = None,
        run_time: float = 1.0,
        rate_func: Callable | str | None = None,
        lag_ratio: float = 0.0,
        remover: bool = False,
        introducer: bool = False,
        name: str | None = None,
    ):
        self.mobject = mobject
        self.run_time = float(run_time)
        self.rate_name, self.rate_func = rate_module.get(rate_func)
        self.lag_ratio = float(lag_ratio)
        self.remover = remover
        self.introducer = introducer
        self.name = name or self.__class__.__name__
        self._begun = False

    # -- lifecycle ---------------------------------------------------------

    def begin(self) -> None:
        """Prepare state.  Must leave point-array structure fixed for the rest
        of the animation, so that keyframes line up."""
        self._begun = True

    def interpolate(self, alpha: float) -> None:
        raise NotImplementedError

    def finish(self) -> None:
        self.interpolate(1.0)

    def clean_up(self, scene) -> None:
        """Hook for animations that add or remove mobjects."""

    # -- what the scene needs to know --------------------------------------

    def mobjects(self) -> list[Shape]:
        return [self.mobject] if self.mobject is not None else []

    def introduced(self) -> list[Shape]:
        return self.mobjects() if self.introducer else []

    def removed(self) -> list[Shape]:
        return self.mobjects() if self.remover else []

    # -- sugar -------------------------------------------------------------

    def set_run_time(self, t: float) -> "Animation":
        self.run_time = float(t)
        return self

    def __repr__(self) -> str:
        return f"{self.name}({self.mobject!r}, {self.run_time}s)"


class _SubLag:
    """Per-child timing inside a group: child i runs on ``[start, end]``."""

    __slots__ = ("start", "end")

    def __init__(self, start: float, end: float):
        self.start, self.end = start, end

    def alpha(self, a: float) -> float:
        span = self.end - self.start
        if span <= 1e-12:
            return 1.0 if a >= self.end else 0.0
        return float(np.clip((a - self.start) / span, 0.0, 1.0))


class AnimationGroup(Animation):
    """Play several animations together.

    ``lag_ratio`` staggers them: 0 is simultaneous, 1 is strictly sequential,
    values in between overlap.
    """

    def __init__(
        self,
        *animations,
        run_time: float | None = None,
        lag_ratio: float = 0.0,
        rate_func: Callable | str | None = "linear",
        **kwargs,
    ):
        anims = [prepare(a) for a in _flatten(animations)]
        self.animations = anims
        super().__init__(None, run_time=1.0, rate_func=rate_func, lag_ratio=lag_ratio, **kwargs)
        self._layout(run_time)

    def _layout(self, run_time: float | None) -> None:
        """Work out each child's window, then the group's own duration."""
        n = len(self.animations)
        if n == 0:
            self.run_time = float(run_time or 0.0)
            self.timings = []
            return
        # Child i starts after lag_ratio * (duration of child i-1).
        starts, t = [], 0.0
        for a in self.animations:
            starts.append(t)
            t += a.run_time * self.lag_ratio
        total = max(s + a.run_time for s, a in zip(starts, self.animations))
        self.natural_run_time = total
        self.run_time = float(run_time) if run_time is not None else total
        scale = 1.0 / total if total > 0 else 0.0
        self.timings = [_SubLag(s * scale, (s + a.run_time) * scale) for s, a in zip(starts, self.animations)]

    @property
    def sampling(self) -> str:  # type: ignore[override]
        if any(a.sampling == "dense" for a in self.animations):
            return "dense"
        if self.animations and all(a.sampling == "linear" for a in self.animations) and self.lag_ratio == 0:
            return "linear"
        return "normal"

    def begin(self) -> None:
        for a in self.animations:
            a.begin()
        super().begin()

    def interpolate(self, alpha: float) -> None:
        for anim, t in zip(self.animations, self.timings):
            anim.interpolate(anim.rate_func(t.alpha(alpha)))

    def mobjects(self) -> list[Shape]:
        out: list[Shape] = []
        for a in self.animations:
            for m in a.mobjects():
                if m not in out:
                    out.append(m)
        return out

    def introduced(self) -> list[Shape]:
        return _dedup(m for a in self.animations for m in a.introduced())

    def removed(self) -> list[Shape]:
        return _dedup(m for a in self.animations for m in a.removed())

    def clean_up(self, scene) -> None:
        for a in self.animations:
            a.clean_up(scene)


class Succession(AnimationGroup):
    """Play animations strictly one after another."""

    def __init__(self, *animations, **kwargs):
        kwargs["lag_ratio"] = 1.0
        super().__init__(*animations, **kwargs)


class LaggedStart(AnimationGroup):
    """Overlapping cascade -- the workhorse for revealing lists and formulas."""

    def __init__(self, *animations, lag_ratio: float = 0.15, **kwargs):
        super().__init__(*animations, lag_ratio=lag_ratio, **kwargs)


class LaggedStartMap(LaggedStart):
    """``LaggedStartMap(FadeIn, group)`` -- one animation per submobject."""

    def __init__(self, factory: Callable, mobject: Shape, lag_ratio: float = 0.15, **kwargs):
        anim_kwargs = {k: kwargs.pop(k) for k in list(kwargs) if k in ("run_time", "rate_func")}
        children = list(mobject.submobjects) or [mobject]
        super().__init__(*[factory(m, **kwargs) for m in children], lag_ratio=lag_ratio, **anim_kwargs)


class Wait(Animation):
    """Hold the current state.  ``scene.wait(t)`` uses this."""

    sampling = "linear"

    def __init__(self, run_time: float = 1.0, **kwargs):
        super().__init__(None, run_time=run_time, rate_func="linear", **kwargs)

    def begin(self) -> None:
        self._begun = True

    def interpolate(self, alpha: float) -> None:
        pass

    def mobjects(self) -> list[Shape]:
        return []


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------


def prepare(obj) -> Animation:
    """Coerce ``mob.animate...`` builders and bare mobjects into animations."""
    from .transform import AnimationBuilder

    if isinstance(obj, Animation):
        return obj
    if isinstance(obj, AnimationBuilder):
        return obj.build()
    if isinstance(obj, Shape):
        from .creation import FadeIn

        return FadeIn(obj)
    raise TypeError(f"cannot play {obj!r}")


def _flatten(items) -> list:
    out = []
    for it in items:
        if isinstance(it, (list, tuple)):
            out.extend(_flatten(it))
        elif it is not None:
            out.append(it)
    return out


def _dedup(items: Iterable[Shape]) -> list[Shape]:
    out: list[Shape] = []
    for m in items:
        if m not in out:
            out.append(m)
    return out
