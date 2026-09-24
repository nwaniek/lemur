"""Animations."""

from .base import Animation, AnimationGroup, LaggedStart, LaggedStartMap, Succession, Wait, prepare
from .creation import (
    AddTextLetterByLetter,
    Create,
    DrawBorderThenFill,
    FadeIn,
    FadeOut,
    GrowArrow,
    GrowFromCenter,
    GrowFromEdge,
    GrowFromPoint,
    Reveal,
    ShowPassingFlash,
    SpinInFromNothing,
    Uncreate,
    Unwrite,
    Write,
)
from .indication import ApplyWave, Circumscribe, Flash, FocusOn, Indicate, Pulse, Wiggle
from .transform import (
    AnimationBuilder,
    ApplyFunction,
    ClockwiseTransform,
    CounterclockwiseTransform,
    FadeTransform,
    MoveAlongPath,
    MoveTo,
    ReplacementTransform,
    Restore,
    Rotate,
    Rotating,
    ScaleBy,
    Shift,
    Transform,
    TransformFromCopy,
    align_families,
)

__all__ = [n for n in dir() if not n.startswith("_")]
