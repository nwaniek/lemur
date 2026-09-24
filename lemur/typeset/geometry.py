"""Serialising subpaths to SVG, and measuring them.

Coordinates here are already in the slide's design-box pixel space (y-down): the
one flip from typeset em-space (y-up) happens when the layout engine places a
piece, so the numbers written into ``d`` match what Python computed. See
plans/Plan-SVG.md §4.1.
"""

from __future__ import annotations

from typing import Sequence

import numpy as np

from . import bezier as bz

__all__ = ["fmt", "path_d", "bbox_of"]

#: Decimal places kept in path data. Glyph outlines are stored in em units and
#: scaled up by the font size in the placement matrix, so this is the *emitted*
#: curve fidelity. 4 is already far below a visible pixel fraction at any normal
#: display size; higher mainly helps print/PDF and deep zoom, lower shrinks the
#: file. Set via ``--quality`` (see :func:`set_precision`).
PRECISION = 4


def set_precision(n: int) -> None:
    """Set the emitted coordinate precision (`--quality`)."""
    global PRECISION
    PRECISION = int(n)


def fmt(x: float) -> str:
    """Compact decimal, no exponent, no trailing zeros."""
    s = f"{float(x):.{PRECISION}f}".rstrip("0").rstrip(".")
    return "0" if s in ("", "-", "-0") else s


def path_d(subpaths: Sequence[np.ndarray], closed: Sequence[bool]) -> str:
    """SVG ``d`` string for a list of ``3k+1`` cubic point arrays."""
    out: list[str] = []
    flags = list(closed) + [False] * len(subpaths)
    for sp, is_closed in zip(subpaths, flags):
        if len(sp) == 0:
            continue
        out.append(f"M{fmt(sp[0][0])},{fmt(sp[0][1])}")
        for i in range(bz.curve_count(sp)):
            p1, p2, p3 = sp[3 * i + 1], sp[3 * i + 2], sp[3 * i + 3]
            out.append(f"C{fmt(p1[0])},{fmt(p1[1])} {fmt(p2[0])},{fmt(p2[1])} {fmt(p3[0])},{fmt(p3[1])}")
        if is_closed:
            out.append("Z")
    return "".join(out)


def bbox_of(subpaths: Sequence[np.ndarray]) -> tuple[float, float, float, float]:
    """``(min_x, min_y, max_x, max_y)`` over every point in ``subpaths``.

    A control-hull box over-estimates; for placement we want the real extent, so
    this is a plain point extent (control points of glyph outlines sit close
    enough to the curve for layout). Curve-tight bounds are a later refinement
    (Plan-SVG §4.1).
    """
    xs, ys = [], []
    for sp in subpaths:
        if len(sp) == 0:
            continue
        xs.append(sp[:, 0])
        ys.append(sp[:, 1])
    if not xs:
        return 0.0, 0.0, 0.0, 0.0
    X = np.concatenate(xs)
    Y = np.concatenate(ys)
    return float(X.min()), float(Y.min()), float(X.max()), float(Y.max())
