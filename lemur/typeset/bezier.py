"""The few Bézier helpers the typeset path needs.

Geometry is a list of subpaths, each a ``3k+1`` array of 2-D points: anchors at
indices ``0, 3, 6, …`` with two control points between each pair. Cubics only —
lines and quadratics are elevated on import so downstream code sees one shape.
"""

from __future__ import annotations

import numpy as np

__all__ = ["curve_count", "line_handles", "quadratic_to_cubic"]


def curve_count(points: np.ndarray) -> int:
    """Number of cubic segments in a ``3k+1`` point array."""
    return max(0, (len(points) - 1) // 3)


def line_handles(anchors: np.ndarray) -> np.ndarray:
    """``3k+1`` points describing straight segments through ``anchors``.

    Each straight edge is expressed as a cubic with its controls at the 1/3 and
    2/3 points, so a polyline shares the same representation as a curve.
    """
    anchors = np.asarray(anchors, dtype=float)
    if len(anchors) < 2:
        return anchors.copy()
    out = [anchors[0]]
    for i in range(len(anchors) - 1):
        p, q = anchors[i], anchors[i + 1]
        out.extend([p + (q - p) / 3, p + 2 * (q - p) / 3, q])
    return np.array(out)


def quadratic_to_cubic(p0, p1, p2) -> np.ndarray:
    """Exact degree elevation of a quadratic Bézier to a cubic."""
    p0, p1, p2 = (np.asarray(p, dtype=float) for p in (p0, p1, p2))
    return np.array([p0, p0 + 2 / 3 * (p1 - p0), p2 + 2 / 3 * (p1 - p2), p2])
