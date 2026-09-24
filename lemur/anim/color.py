"""Colour handling.

A colour is stored as an RGBA tuple of floats in ``[0, 1]``.  Anything that
looks like a colour is accepted at the API surface: ``"#rgb"``, ``"#rrggbb"``,
``"#rrggbbaa"``, ``"red"``, ``(r, g, b)``, ``(r, g, b, a)``, or an existing
:class:`Color`.
"""

from __future__ import annotations

from typing import Iterable

import numpy as np

from . import constants as C

__all__ = ["Color", "to_color", "interpolate_color", "color_gradient", "lighten", "darken"]


_NAMED: dict[str, str] = {
    "blue": C.BLUE,
    "teal": C.TEAL,
    "green": C.GREEN,
    "yellow": C.YELLOW,
    "orange": C.ORANGE,
    "red": C.RED,
    "maroon": C.MAROON,
    "purple": C.PURPLE,
    "pink": C.PINK,
    "grey": C.GREY,
    "gray": C.GREY,
    "black": C.BLACK,
    "white": C.WHITE,
    "light_grey": C.LIGHT_GREY,
    "light_gray": C.LIGHT_GREY,
    "dark_grey": C.DARK_GREY,
    "dark_gray": C.DARK_GREY,
    "light_blue": C.LIGHT_BLUE,
    "dark_blue": C.DARK_BLUE,
    "transparent": "#00000000",
    "none": "#00000000",
}


class Color:
    """An immutable RGBA colour."""

    __slots__ = ("rgba",)

    def __init__(self, value: "ColorLike" = "#000000", alpha: float | None = None):
        rgba = _parse(value)
        if alpha is not None:
            rgba = (rgba[0], rgba[1], rgba[2], float(alpha))
        self.rgba = rgba

    # -- accessors ---------------------------------------------------------
    @property
    def r(self) -> float:
        return self.rgba[0]

    @property
    def g(self) -> float:
        return self.rgba[1]

    @property
    def b(self) -> float:
        return self.rgba[2]

    @property
    def a(self) -> float:
        return self.rgba[3]

    @property
    def rgb(self) -> tuple[float, float, float]:
        return self.rgba[:3]

    def with_alpha(self, alpha: float) -> "Color":
        return Color(self.rgba[:3], alpha)

    # -- conversions -------------------------------------------------------
    def hex(self) -> str:
        """``#rrggbb`` (alpha is dropped; SVG carries it separately)."""
        r, g, b, _ = self.rgba
        return "#{:02x}{:02x}{:02x}".format(*(int(round(v * 255)) for v in (r, g, b)))

    def hexa(self) -> str:
        return self.hex() + "{:02x}".format(int(round(self.a * 255)))

    def to_list(self) -> list[float]:
        return list(self.rgba)

    def __iter__(self):
        return iter(self.rgba)

    def __eq__(self, other) -> bool:
        return isinstance(other, Color) and self.rgba == other.rgba

    def __hash__(self) -> int:
        return hash(self.rgba)

    def __repr__(self) -> str:
        return f"Color({self.hexa()!r})"

    # -- tweaks ------------------------------------------------------------
    def lighten(self, amount: float = 0.3) -> "Color":
        return lighten(self, amount)

    def darken(self, amount: float = 0.3) -> "Color":
        return darken(self, amount)


ColorLike = "Color | str | Iterable[float] | None"


def _parse(value) -> tuple[float, float, float, float]:
    if isinstance(value, Color):
        return value.rgba
    if value is None:
        return (0.0, 0.0, 0.0, 0.0)
    if isinstance(value, str):
        s = value.strip().lower()
        s = _NAMED.get(s, s)
        if not s.startswith("#"):
            raise ValueError(f"unknown colour: {value!r}")
        h = s[1:]
        if len(h) == 3:
            h = "".join(c * 2 for c in h)
        elif len(h) == 4:
            h = "".join(c * 2 for c in h)
        if len(h) == 6:
            h += "ff"
        if len(h) != 8:
            raise ValueError(f"malformed hex colour: {value!r}")
        try:
            vals = [int(h[i : i + 2], 16) / 255 for i in (0, 2, 4, 6)]
        except ValueError as exc:
            raise ValueError(f"malformed hex colour: {value!r}") from exc
        return tuple(vals)  # type: ignore[return-value]
    seq = [float(v) for v in value]
    if len(seq) == 3:
        seq.append(1.0)
    if len(seq) != 4:
        raise ValueError(f"colour needs 3 or 4 components, got {len(seq)}")
    if max(seq) > 1.0001:  # tolerate 0..255 input
        seq = [v / 255 for v in seq[:3]] + [seq[3] if seq[3] <= 1 else seq[3] / 255]
    return tuple(min(1.0, max(0.0, v)) for v in seq)  # type: ignore[return-value]


def to_color(value) -> Color:
    """Coerce ``value`` to a :class:`Color` (idempotent)."""
    return value if isinstance(value, Color) else Color(value)


def interpolate_color(a, b, alpha: float) -> Color:
    """Linear RGBA blend."""
    ca, cb = to_color(a).rgba, to_color(b).rgba
    return Color(tuple(x + (y - x) * alpha for x, y in zip(ca, cb)))


def color_gradient(colors, n: int) -> list[Color]:
    """``n`` colours evenly sampled from the piecewise-linear ramp ``colors``."""
    cols = [to_color(c) for c in colors]
    if n <= 0:
        return []
    if len(cols) == 1 or n == 1:
        return [cols[0]] * n
    out = []
    for i in range(n):
        t = i / (n - 1) * (len(cols) - 1)
        lo = min(int(t), len(cols) - 2)
        out.append(interpolate_color(cols[lo], cols[lo + 1], t - lo))
    return out


def lighten(color, amount: float = 0.3) -> Color:
    return interpolate_color(color, Color("#ffffff", to_color(color).a), amount)


def darken(color, amount: float = 0.3) -> Color:
    return interpolate_color(color, Color("#000000", to_color(color).a), amount)


def rgba_array(colors) -> np.ndarray:
    return np.array([to_color(c).rgba for c in colors], dtype=float)
