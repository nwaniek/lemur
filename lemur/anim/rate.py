"""Rate (easing) functions.

Every function here has an equivalent in the deck's player
(``lemur/assets/svg/runtime.js``, ``EASE``).  Keyframes are sampled uniformly in *alpha*;
the rate function is what maps wall-clock time onto alpha at playback, so the
two implementations must agree.  Add one here, add it there.
"""

from __future__ import annotations

import math

__all__ = ["get", "names", "linear", "smooth", "rush_into", "rush_from", "there_and_back"]


def linear(t: float) -> float:
    return t


def smooth(t: float) -> float:
    """Smootherstep -- zero first *and* second derivative at both ends."""
    return t * t * t * (10 + t * (-15 + 6 * t))


def smoothstep(t: float) -> float:
    return t * t * (3 - 2 * t)


def ease_in_quad(t: float) -> float:
    return t * t


def ease_out_quad(t: float) -> float:
    return 1 - (1 - t) ** 2


def ease_in_out_quad(t: float) -> float:
    return 2 * t * t if t < 0.5 else 1 - (-2 * t + 2) ** 2 / 2


def ease_in_cubic(t: float) -> float:
    return t**3


def ease_out_cubic(t: float) -> float:
    return 1 - (1 - t) ** 3


def ease_in_out_cubic(t: float) -> float:
    return 4 * t**3 if t < 0.5 else 1 - (-2 * t + 2) ** 3 / 2


def ease_in_expo(t: float) -> float:
    return 0.0 if t <= 0 else 2 ** (10 * t - 10)


def ease_out_expo(t: float) -> float:
    return 1.0 if t >= 1 else 1 - 2 ** (-10 * t)


def ease_out_back(t: float) -> float:
    c1, c3 = 1.70158, 2.70158
    return 1 + c3 * (t - 1) ** 3 + c1 * (t - 1) ** 2


def ease_out_elastic(t: float) -> float:
    if t <= 0 or t >= 1:
        return float(t)
    c4 = 2 * math.pi / 3
    return 2 ** (-10 * t) * math.sin((t * 10 - 0.75) * c4) + 1


def ease_out_bounce(t: float) -> float:
    n1, d1 = 7.5625, 2.75
    if t < 1 / d1:
        return n1 * t * t
    if t < 2 / d1:
        t -= 1.5 / d1
        return n1 * t * t + 0.75
    if t < 2.5 / d1:
        t -= 2.25 / d1
        return n1 * t * t + 0.9375
    t -= 2.625 / d1
    return n1 * t * t + 0.984375


def rush_into(t: float) -> float:
    """Accelerate, then stop abruptly (good for things arriving)."""
    return 2 * smooth(t / 2)


def rush_from(t: float) -> float:
    """Start abruptly, then decelerate (good for things leaving)."""
    return 2 * smooth(t / 2 + 0.5) - 1


def slow_into(t: float) -> float:
    return math.sqrt(max(0.0, 1 - (1 - t) ** 2))


def double_smooth(t: float) -> float:
    return 0.5 * smooth(2 * t) if t < 0.5 else 0.5 * (1 + smooth(2 * t - 1))


def there_and_back(t: float) -> float:
    return smooth(2 * t) if t < 0.5 else smooth(2 - 2 * t)


def there_and_back_with_pause(t: float) -> float:
    if t < 1 / 3:
        return smooth(3 * t)
    if t < 2 / 3:
        return 1.0
    return smooth(3 - 3 * t)


def wiggle(t: float) -> float:
    return there_and_back(t) * math.sin(6 * math.pi * t)


#: Steepness of `exponential_decay`; the normalisation below is what makes
#: the curve actually reach 1 at t = 1 rather than merely approaching it.
_DECAY_K = 6.9
_DECAY_NORM = 1 - math.exp(-_DECAY_K)


def exponential_decay(t: float) -> float:
    return (1 - math.exp(-_DECAY_K * t)) / _DECAY_NORM


_TABLE = {
    "linear": linear,
    "smooth": smooth,
    "smoothstep": smoothstep,
    "ease_in_quad": ease_in_quad,
    "ease_out_quad": ease_out_quad,
    "ease_in_out_quad": ease_in_out_quad,
    "ease_in_cubic": ease_in_cubic,
    "ease_out_cubic": ease_out_cubic,
    "ease_in_out_cubic": ease_in_out_cubic,
    "ease_in_expo": ease_in_expo,
    "ease_out_expo": ease_out_expo,
    "ease_out_back": ease_out_back,
    "ease_out_elastic": ease_out_elastic,
    "ease_out_bounce": ease_out_bounce,
    "rush_into": rush_into,
    "rush_from": rush_from,
    "slow_into": slow_into,
    "double_smooth": double_smooth,
    "there_and_back": there_and_back,
    "there_and_back_with_pause": there_and_back_with_pause,
    "wiggle": wiggle,
    "exponential_decay": exponential_decay,
}


def names() -> list[str]:
    return sorted(_TABLE)


def get(func) -> tuple[str, callable]:
    """Resolve a rate function to ``(name, callable)``.

    A bare callable is allowed but has no name the browser knows, so it gets
    baked into the samples and played back linearly.
    """
    if func is None:
        return "smooth", smooth
    if isinstance(func, str):
        if func not in _TABLE:
            raise ValueError(f"unknown rate function {func!r}; choose from {names()}")
        return func, _TABLE[func]
    for name, fn in _TABLE.items():
        if fn is func:
            return name, fn
    return "", func
