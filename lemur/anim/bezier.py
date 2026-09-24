"""Cubic Bézier utilities.

Everything in wanim that has a shape is a list of *subpaths*, and a subpath is
an array of ``3k+1`` points laid out as::

    A0  C0a C0b  A1  C1a C1b  A2  ...

i.e. anchors at indices ``0, 3, 6, ...`` and two control points between each
pair.  Curve ``i`` is therefore ``points[3i : 3i+4]``.
"""

from __future__ import annotations

import numpy as np

__all__ = [
    "bezier",
    "split_cubic",
    "partial_cubic",
    "subdivide_cubic",
    "cubic_length",
    "interpolate",
    "inverse_interpolate",
    "catmull_rom_handles",
    "line_handles",
    "quadratic_to_cubic",
    "curve_count",
    "insert_n_curves_to_points",
]

EPS = 1e-9


# --------------------------------------------------------------------------
# evaluation
# --------------------------------------------------------------------------


def bezier(points: np.ndarray, t):
    """Evaluate a Bézier curve of any degree at ``t`` (scalar or array)."""
    pts = np.asarray(points, dtype=float)
    n = len(pts) - 1
    t = np.asarray(t, dtype=float)
    result = np.zeros(t.shape + (pts.shape[-1],))
    for i, p in enumerate(pts):
        coeff = _binom(n, i) * (1 - t) ** (n - i) * t**i
        result += coeff[..., None] * p
    return result


def _binom(n: int, k: int) -> float:
    from math import comb

    return float(comb(n, k))


def curve_count(points: np.ndarray) -> int:
    """Number of cubic segments in a ``3k+1`` point array."""
    return max(0, (len(points) - 1) // 3)


# --------------------------------------------------------------------------
# splitting
# --------------------------------------------------------------------------


def split_cubic(points: np.ndarray, t: float) -> tuple[np.ndarray, np.ndarray]:
    """de Casteljau split of one cubic into two cubics at parameter ``t``."""
    p0, p1, p2, p3 = np.asarray(points, dtype=float)
    a = p0 + (p1 - p0) * t
    b = p1 + (p2 - p1) * t
    c = p2 + (p3 - p2) * t
    d = a + (b - a) * t
    e = b + (c - b) * t
    f = d + (e - d) * t
    return np.array([p0, a, d, f]), np.array([f, e, c, p3])


def partial_cubic(points: np.ndarray, a: float, b: float) -> np.ndarray:
    """The piece of one cubic between parameters ``a`` and ``b``."""
    pts = np.asarray(points, dtype=float)
    if b <= a:
        p = bezier(pts, a)
        return np.array([p, p, p, p])
    if b < 1.0:
        pts = split_cubic(pts, b)[0]
    if a > 0.0:
        pts = split_cubic(pts, a / b if b > EPS else 0.0)[1]
    return pts


def subdivide_cubic(points: np.ndarray, n: int) -> np.ndarray:
    """Split one cubic into ``n`` cubics, returned as a ``3n+1`` point array."""
    if n <= 1:
        return np.asarray(points, dtype=float)
    out = [np.asarray(points, dtype=float)[0]]
    rest = np.asarray(points, dtype=float)
    remaining = n
    while remaining > 1:
        left, rest = split_cubic(rest, 1.0 / remaining)
        out.extend(left[1:])
        remaining -= 1
    out.extend(rest[1:])
    return np.array(out)


# --------------------------------------------------------------------------
# measurement
# --------------------------------------------------------------------------


def cubic_length(points: np.ndarray, samples: int = 12) -> float:
    """Polyline approximation of a cubic's arc length."""
    ts = np.linspace(0.0, 1.0, samples + 1)
    pts = bezier(np.asarray(points, dtype=float), ts)
    return float(np.linalg.norm(np.diff(pts, axis=0), axis=1).sum())


def curve_lengths(points: np.ndarray, samples: int = 12) -> np.ndarray:
    """Arc length of every cubic in a ``3k+1`` point array.

    Vectorised over curves: a decimated ODE trajectory still has thousands of
    segments, and this runs on every progressive-draw sample.
    """
    pts = np.asarray(points, dtype=float)
    n = curve_count(pts)
    if n == 0:
        return np.zeros(0)
    P0, P1, P2, P3 = (pts[k : 3 * n + k : 3] for k in (0, 1, 2, 3))
    t = np.linspace(0.0, 1.0, samples + 1)[:, None, None]
    u = 1 - t
    # (samples+1, n, 2)
    curve = u**3 * P0 + 3 * u**2 * t * P1 + 3 * u * t**2 * P2 + t**3 * P3
    return np.linalg.norm(np.diff(curve, axis=0), axis=2).sum(axis=0)


# --------------------------------------------------------------------------
# interpolation helpers
# --------------------------------------------------------------------------


def interpolate(a, b, alpha):
    return np.asarray(a) + (np.asarray(b) - np.asarray(a)) * alpha


def inverse_interpolate(a, b, value):
    return (np.asarray(value) - a) / (b - a)


# --------------------------------------------------------------------------
# handle generation
# --------------------------------------------------------------------------


def line_handles(anchors: np.ndarray) -> np.ndarray:
    """``3k+1`` points describing straight segments through ``anchors``."""
    anchors = np.asarray(anchors, dtype=float)
    if len(anchors) < 2:
        return anchors.copy()
    out = [anchors[0]]
    for i in range(len(anchors) - 1):
        p, q = anchors[i], anchors[i + 1]
        out.extend([p + (q - p) / 3, p + 2 * (q - p) / 3, q])
    return np.array(out)


def catmull_rom_handles(anchors: np.ndarray, closed: bool = False, alpha: float = 0.5) -> np.ndarray:
    """Smooth ``3k+1`` point array through ``anchors``.

    Uses a centripetal Catmull-Rom spline (``alpha=0.5``), which is C1 and --
    unlike the uniform variant or a natural cubic spline -- provably free of
    cusps and self-intersections within a segment.  That matters for plots,
    where a natural spline happily overshoots on steep data.
    """
    P = np.asarray(anchors, dtype=float)
    if len(P) < 2:
        return P.copy()
    if len(P) == 2 and not closed:
        return line_handles(P)

    if closed:
        # Wrap one point on each side; the loop below then emits every segment.
        ext = np.vstack([P[-1], P, P[0], P[1]])
        n_seg = len(P)
    else:
        # Reflect the end points so the first/last segment gets a sane tangent.
        ext = np.vstack([2 * P[0] - P[1], P, 2 * P[-1] - P[-2]])
        n_seg = len(P) - 1

    # Centripetal knot spacing.
    d = np.linalg.norm(np.diff(ext, axis=0), axis=1)
    d = np.maximum(d, EPS) ** alpha
    t = np.concatenate([[0.0], np.cumsum(d)])

    out = [ext[1]]
    for i in range(n_seg):
        p0, p1, p2, p3 = ext[i : i + 4]
        t0, t1, t2, t3 = t[i : i + 4]
        dt1 = max(t2 - t1, EPS)
        m1 = (p2 - p0) * dt1 / max(t2 - t0, EPS)
        m2 = (p3 - p1) * dt1 / max(t3 - t1, EPS)
        out.extend([p1 + m1 / 3, p2 - m2 / 3, p2])
    return np.array(out)


def quadratic_to_cubic(p0, p1, p2) -> np.ndarray:
    """Exact degree elevation of a quadratic Bézier."""
    p0, p1, p2 = (np.asarray(p, dtype=float) for p in (p0, p1, p2))
    return np.array([p0, p0 + 2 / 3 * (p1 - p0), p2 + 2 / 3 * (p1 - p2), p2])


# --------------------------------------------------------------------------
# alignment (for morphing)
# --------------------------------------------------------------------------


def insert_n_curves_to_points(points: np.ndarray, n: int) -> np.ndarray:
    """Return ``points`` re-expressed with ``n`` extra cubic segments.

    Segments are split in proportion to their arc length, so the added detail
    lands where the shape actually is -- morphs between a long line and a
    circle stay well distributed instead of bunching at one end.
    """
    points = np.asarray(points, dtype=float)
    if n <= 0:
        return points.copy()
    k = curve_count(points)
    if k == 0:
        # Degenerate (single point): fabricate n+1 zero-length curves.
        p = points[0] if len(points) else np.zeros(2)
        return np.repeat(p[None, :], 3 * (n + 1) + 1, axis=0)

    lengths = curve_lengths(points)
    total = lengths.sum()
    if total < EPS:
        # All-degenerate: distribute evenly.
        counts = np.ones(k, dtype=int)
        for i in range(n):
            counts[i % k] += 1
    else:
        # Largest-remainder apportionment of the n new splits.
        want = lengths / total * n
        counts = np.floor(want).astype(int)
        rem = n - counts.sum()
        if rem > 0:
            order = np.argsort(-(want - counts))
            counts[order[:rem]] += 1
        counts += 1

    out = [points[0]]
    for i in range(k):
        seg = subdivide_cubic(points[3 * i : 3 * i + 4], int(counts[i]))
        out.extend(seg[1:])
    return np.array(out)
