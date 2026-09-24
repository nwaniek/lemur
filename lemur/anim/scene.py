"""``Anim`` -- the API a lemur ``!anim`` module is written against.

Subclass :class:`Anim` and override :meth:`build`: create and animate shapes,
and call ``self.next()`` to mark a beat (the presenter stops there -- one beat =
one slide step). :meth:`render` runs it and returns the keyframe IR that the
emitter bakes into the slide's viewport. Slide chrome (title, footer, background)
is lemur's job, not the animation's -- an ``Anim`` is pure animation content in a
world/camera coordinate space.
"""

from __future__ import annotations

import math
from typing import Callable, Iterable

import numpy as np

from . import constants as C
from . import ir as _ir
from . import rate as rate_module
from .animation.base import Animation, AnimationGroup, Wait, prepare
from .camera import Camera
from .mobject import Shape, VShape

__all__ = ["Anim", "registered_anims", "clear_registry"]


_REGISTRY: list[type] = []


def registered_anims() -> list[type]:
    return list(_REGISTRY)


def clear_registry() -> None:
    _REGISTRY.clear()


class Anim:
    """Build and animate shapes, and record what happened. Subclassing registers
    the class (so the emitter can find the animation in a module)."""

    #: Set to False to leave an animation out of the build.
    enabled: bool = True

    def __init_subclass__(cls, register: bool = True, **kwargs):
        super().__init_subclass__(**kwargs)
        if register and not cls.__name__.startswith("_"):
            _REGISTRY.append(cls)

    def __init__(self):
        self.camera = Camera()
        self.mobjects: list[Shape] = []
        self.recorder = _ir.Recorder()
        # False: compute only each animation's end state, without keyframes
        # (for callers that want a still picture of the result).
        self.recording = True
        self.time = 0.0
        self.beats: list[dict] = []
        self._chrome: list[Shape] = []
        self._finalised = False

    # -- user hook ---------------------------------------------------------

    def build(self) -> None:
        """Override this: create shapes, `self.play(...)` animations, `self.next()`
        beats."""

    # -- scene contents ----------------------------------------------------

    def add(self, *mobjects: Shape) -> "Anim":
        """Put mobjects on the slide immediately (no animation)."""
        changed = False
        for m in _flat(mobjects):
            if m not in self.mobjects:
                self.mobjects.append(m)
                changed = True
        if changed:
            self._mark_instant()
        return self

    def remove(self, *mobjects: Shape) -> "Anim":
        changed = False
        for m in _flat(mobjects):
            if m in self.mobjects:
                self.mobjects.remove(m)
                changed = True
        if changed:
            self._mark_instant()
        return self

    def clear(self, keep_chrome: bool = True) -> "Anim":
        self.mobjects = [m for m in self.mobjects if keep_chrome and m in self._chrome]
        self._mark_instant()
        return self

    def bring_to_front(self, *mobjects: Shape) -> "Anim":
        """Draw these above everything else (later arguments on top). Applies to
        each shape's whole family, so groups move as a unit."""
        top = max((f.z_index for m in self.mobjects for f in m.family), default=0.0)
        for i, m in enumerate(_flat(mobjects)):
            for f in m.family:
                f.set_z_index(top + 1 + i)
        return self

    def bring_to_back(self, *mobjects: Shape) -> "Anim":
        """Draw these below everything else (later arguments further back)."""
        bottom = min((f.z_index for m in self.mobjects for f in m.family), default=0.0)
        for i, m in enumerate(_flat(mobjects)):
            for f in m.family:
                f.set_z_index(bottom - 1 - i)
        return self

    def add_chrome(self, *mobjects: Shape) -> "Anim":
        """Add slide furniture (title bar, page number) that ``clear`` keeps."""
        self._chrome.extend(_flat(mobjects))
        return self.add(*mobjects)

    # -- time --------------------------------------------------------------

    def play(
        self,
        *animations,
        run_time: float | None = None,
        rate_func=None,
        lag_ratio: float = 0.0,
        **kwargs,
    ) -> "Anim":
        """Run animations, recording keyframes as they go."""
        anims = [prepare(a) for a in _flat_anims(animations)]
        if not anims:
            return self
        if len(anims) == 1 and not kwargs and lag_ratio == 0.0:
            anim = anims[0]
            if run_time is not None:
                anim.run_time = float(run_time)
            if rate_func is not None:
                anim.rate_name, anim.rate_func = rate_module.get(rate_func)
        else:
            anim = AnimationGroup(*anims, run_time=run_time, lag_ratio=lag_ratio, rate_func=rate_func or "linear", **kwargs)

        anim.begin()
        for m in anim.introduced():
            if m not in self.mobjects:
                self.mobjects.append(m)

        if self.recording:
            n = self._sample_count(anim)
            alphas = [i / (n - 1) for i in range(n)] if n > 1 else [1.0]
            self.recorder.open_segment(self.time, self.time + anim.run_time, anim.rate_name or "linear", alphas)
            dt = anim.run_time / max(n - 1, 1)
            for i, a in enumerate(alphas):
                anim.interpolate(a)
                self._run_updaters(dt if i else 0.0)
                self.recorder.sample(self.mobjects, self.camera.state())
        else:
            self._run_updaters(anim.run_time)

        anim.finish()
        anim.clean_up(self)
        for m in anim.removed():
            if m in self.mobjects:
                self.mobjects.remove(m)
        self.time += anim.run_time
        return self

    def _sample_count(self, anim: Animation) -> int:
        rate = _ir.SAMPLE_RATE.get(getattr(anim, "sampling", "normal"), 24.0)
        if self._has_updaters():
            rate = max(rate, _ir.SAMPLE_RATE["normal"])
        if rate <= 0:
            return 2
        return int(min(_ir.MAX_SAMPLES, max(2, math.ceil(anim.run_time * rate) + 1)))

    def wait(self, duration: float = 1.0) -> "Anim":
        """Hold the current image."""
        if duration <= 0:
            return self
        if self.recording:
            if self._has_updaters():
                return self.play(Wait(duration))
            self.recorder.open_segment(self.time, self.time + duration, "linear", [0.0, 1.0])
            self.recorder.sample(self.mobjects, self.camera.state())
            self.recorder.sample(self.mobjects, self.camera.state())
        self.time += duration
        return self

    def pause(self, duration: float = 0.25) -> "Anim":
        return self.wait(duration)

    def next(self, label: str | None = None) -> "Anim":
        """Mark a stop: the presenter pauses here until the next key press.

        This is the unit of "one click" in a talk; the PDF exporter can also
        turn each one into its own handout page.
        """
        self._mark_instant()
        self.beats.append({"t": round(self.time, 5), "label": label})
        return self

    # -- updaters ----------------------------------------------------------

    def _has_updaters(self) -> bool:
        return any(m.has_updaters() for m in self.mobjects)

    def _run_updaters(self, dt: float) -> None:
        for m in self.mobjects:
            m.update(dt)

    def _mark_instant(self) -> None:
        """Record a zero-length segment so instant changes land in the IR."""
        if self._finalised or not self.recording:
            return
        # Let updater-driven mobjects settle first: an animation's finish() may
        # have left stale geometry (e.g. FadeIn restores the shape captured at
        # begin), and this still frame — the beat's resting state and the baked
        # final frame — should reflect what the updaters actually produce.
        if self._has_updaters():
            self._run_updaters(0.0)
        self.recorder.open_segment(self.time, self.time, "linear", [1.0])
        self.recorder.sample(self.mobjects, self.camera.state())

    # -- convenience -------------------------------------------------------

    def play_many(self, factory: Callable, mobjects: Iterable[Shape], lag_ratio: float = 0.15, **kwargs) -> "Anim":
        from .animation.base import LaggedStart

        return self.play(LaggedStart(*[factory(m) for m in mobjects], lag_ratio=lag_ratio, **kwargs))

    def focus(self, mobject: Shape, buff: float = 0.6, run_time: float = 1.2) -> "Anim":
        """Animate the camera onto a mobject."""
        target = self.camera.frame.copy()
        target.focus_on(mobject, buff=buff)
        from .animation.transform import Transform

        return self.play(Transform(self.camera.frame, target, run_time=run_time))

    def reset_camera(self, run_time: float = 1.2) -> "Anim":
        target = self.camera.frame.copy()
        target.reset()
        from .animation.transform import Transform

        return self.play(Transform(self.camera.frame, target, run_time=run_time))

    # -- output ------------------------------------------------------------

    def render(self) -> dict:
        """Run ``build`` and return this animation's IR — ``{nodes, tracks,
        duration, defs, beats, camera}``. The emitter bakes it into the viewport."""
        self.build()
        # Always end on a still frame so the last state is recorded.
        self._mark_instant()
        self._finalised = True

        defs: dict[str, str] = {}
        data = _ir.build_slide(self.recorder, defs, self.time)
        data["defs"] = defs
        data["beats"] = self.beats
        data["camera"] = _ir.build_camera_tracks(self.recorder)
        return data

    def snapshot(self) -> list[Shape]:
        """Everything currently on the animation, for still-frame rendering."""
        return list(self.mobjects)


def _flat(items) -> list[Shape]:
    out: list[Shape] = []
    for it in items:
        if isinstance(it, Shape):
            out.append(it)
        elif isinstance(it, (list, tuple, set)):
            out.extend(_flat(it))
        elif it is not None:
            raise TypeError(f"not a mobject: {it!r}")
    return out


def _flat_anims(items) -> list:
    out = []
    for it in items:
        if isinstance(it, (list, tuple)):
            out.extend(_flat_anims(it))
        elif it is not None:
            out.append(it)
    return out


def _humanise(name: str) -> str:
    """``LorenzAttractor`` -> ``Lorenz Attractor``."""
    out = []
    for i, ch in enumerate(name):
        if i and ch.isupper() and not name[i - 1].isupper():
            out.append(" ")
        out.append(ch)
    return "".join(out).replace("_", " ").strip()
