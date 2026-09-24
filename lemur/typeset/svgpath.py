"""A small, complete SVG path-data parser.

Used to import the SVG that ``dvisvgm`` produces for LaTeX maths. Every command
is converted to cubic Béziers in the ``3k+1`` layout the rest of the typeset
path uses. Mined from wanim (plans/Plan-SVG.md §11).
"""

from __future__ import annotations

import re

import numpy as np

from . import bezier as bz

__all__ = ["parse_path", "parse_transform", "apply_transform"]

_TOKEN = re.compile(r"[MmZzLlHhVvCcSsQqTtAa]|[-+]?(?:\d*\.\d+|\d+\.?)(?:[eE][-+]?\d+)?")


def _tokens(d: str):
    for m in _TOKEN.finditer(d):
        t = m.group()
        yield t if t.isalpha() else float(t)


def parse_path(d: str) -> tuple[list[np.ndarray], list[bool]]:
    """Parse an SVG ``d`` string into ``(subpaths, closed_flags)``."""
    toks = list(_tokens(d))
    i = 0
    subpaths: list[np.ndarray] = []
    closed: list[bool] = []

    pts: list[np.ndarray] = []  # current subpath, 3k+1 layout
    cur = np.zeros(2)
    start = np.zeros(2)
    prev_cubic_ctrl: np.ndarray | None = None
    prev_quad_ctrl: np.ndarray | None = None
    cmd = ""

    def flush(is_closed: bool) -> None:
        nonlocal pts
        if len(pts) >= 4:
            subpaths.append(np.array(pts))
            closed.append(is_closed)
        pts = []

    def curve_to(c1, c2, end) -> None:
        pts.extend([np.asarray(c1, float), np.asarray(c2, float), np.asarray(end, float)])

    def line_to(end) -> None:
        e = np.asarray(end, float)
        curve_to(cur + (e - cur) / 3, cur + 2 * (e - cur) / 3, e)

    def take(n: int) -> list[float]:
        nonlocal i
        vals = toks[i : i + n]
        i += n
        if len(vals) < n or any(isinstance(v, str) for v in vals):
            raise ValueError(f"malformed path data near token {i}")
        return vals  # type: ignore[return-value]

    while i < len(toks):
        if isinstance(toks[i], str):
            cmd = toks[i]
            i += 1
            if cmd in "Zz":
                if pts:
                    if not np.allclose(cur, start, atol=1e-9):
                        line_to(start)
                    flush(True)
                cur = start.copy()
                prev_cubic_ctrl = prev_quad_ctrl = None
                continue
        elif cmd in ("M", "m"):
            cmd = "L" if cmd == "M" else "l"  # repeated moveto pairs are linetos
        elif not cmd:
            raise ValueError("path data does not start with a command")

        rel = cmd.islower()
        base = cur if rel else np.zeros(2)
        c = cmd.upper()

        if c == "M":
            x, y = take(2)
            if pts:
                flush(False)
            cur = base + np.array([x, y])
            start = cur.copy()
            pts = [cur.copy()]
            prev_cubic_ctrl = prev_quad_ctrl = None
        elif c in ("L", "H", "V"):
            if c == "L":
                x, y = take(2)
                end = base + np.array([x, y])
            elif c == "H":
                (x,) = take(1)
                end = np.array([(cur[0] if rel else 0.0) + x, cur[1]])
            else:
                (y,) = take(1)
                end = np.array([cur[0], (cur[1] if rel else 0.0) + y])
            line_to(end)
            cur = end
            prev_cubic_ctrl = prev_quad_ctrl = None
        elif c in ("C", "S"):
            if c == "C":
                x1, y1, x2, y2, x, y = take(6)
                c1 = base + np.array([x1, y1])
            else:
                x2, y2, x, y = take(4)
                c1 = 2 * cur - prev_cubic_ctrl if prev_cubic_ctrl is not None else cur.copy()
            c2 = base + np.array([x2, y2])
            end = base + np.array([x, y])
            curve_to(c1, c2, end)
            cur, prev_cubic_ctrl, prev_quad_ctrl = end, c2, None
        elif c in ("Q", "T"):
            if c == "Q":
                x1, y1, x, y = take(4)
                q = base + np.array([x1, y1])
            else:
                x, y = take(2)
                q = 2 * cur - prev_quad_ctrl if prev_quad_ctrl is not None else cur.copy()
            end = base + np.array([x, y])
            cubic = bz.quadratic_to_cubic(cur, q, end)
            curve_to(cubic[1], cubic[2], cubic[3])
            cur, prev_quad_ctrl, prev_cubic_ctrl = end, q, None
        elif c == "A":
            rx, ry, rot, large, sweep, x, y = take(7)
            end = base + np.array([x, y])
            for seg in _arc_to_cubics(cur, end, rx, ry, np.deg2rad(rot), bool(large), bool(sweep)):
                curve_to(seg[1], seg[2], seg[3])
            cur = end
            prev_cubic_ctrl = prev_quad_ctrl = None
        else:
            raise ValueError(f"unsupported path command {cmd!r}")

    flush(False)
    return subpaths, closed


def _arc_to_cubics(p0, p1, rx, ry, phi, large, sweep) -> list[np.ndarray]:
    """SVG endpoint-parameterised elliptical arc -> list of cubic segments."""
    p0 = np.asarray(p0, float)
    p1 = np.asarray(p1, float)
    if np.allclose(p0, p1) or rx == 0 or ry == 0:
        return [bz.line_handles(np.array([p0, p1]))[0:4]] if not np.allclose(p0, p1) else []
    rx, ry = abs(rx), abs(ry)
    cos_p, sin_p = np.cos(phi), np.sin(phi)
    R = np.array([[cos_p, sin_p], [-sin_p, cos_p]])
    d = R @ ((p0 - p1) / 2)

    # Scale up the radii if they are too small to span the endpoints.
    lam = (d[0] / rx) ** 2 + (d[1] / ry) ** 2
    if lam > 1:
        rx, ry = rx * np.sqrt(lam), ry * np.sqrt(lam)

    num = rx**2 * ry**2 - rx**2 * d[1] ** 2 - ry**2 * d[0] ** 2
    den = rx**2 * d[1] ** 2 + ry**2 * d[0] ** 2
    coef = np.sqrt(max(num, 0.0) / den) * (-1 if large == sweep else 1)
    cp = coef * np.array([rx * d[1] / ry, -ry * d[0] / rx])
    center = R.T @ cp + (p0 + p1) / 2

    def angle_of(pt):
        v = (R @ (pt - center)) / np.array([rx, ry])
        return np.arctan2(v[1], v[0])

    th0 = angle_of(p0)
    th1 = angle_of(p1)
    dth = th1 - th0
    if sweep and dth < 0:
        dth += 2 * np.pi
    elif not sweep and dth > 0:
        dth -= 2 * np.pi

    n = max(1, int(np.ceil(abs(dth) / (np.pi / 2) - 1e-9)))
    step = dth / n
    h = 4 / 3 * np.tan(step / 4)
    out = []
    for k in range(n):
        a0 = th0 + k * step
        a1 = a0 + step

        def pt(a):
            return center + R.T @ (np.array([rx * np.cos(a), ry * np.sin(a)]))

        def tan(a):
            return R.T @ (np.array([-rx * np.sin(a), ry * np.cos(a)]))

        q0, q1 = pt(a0), pt(a1)
        out.append(np.array([q0, q0 + h * tan(a0), q1 - h * tan(a1), q1]))
    return out


# --------------------------------------------------------------------------
# transforms
# --------------------------------------------------------------------------

_XF = re.compile(r"(matrix|translate|scale|rotate|skewX|skewY)\s*\(([^)]*)\)")


def parse_transform(text: str | None) -> np.ndarray:
    """SVG ``transform`` attribute -> 3x3 homogeneous matrix."""
    M = np.eye(3)
    if not text:
        return M
    for name, args in _XF.findall(text):
        v = [float(x) for x in re.split(r"[\s,]+", args.strip()) if x]
        T = np.eye(3)
        if name == "matrix" and len(v) == 6:
            T[:2, :] = np.array([[v[0], v[2], v[4]], [v[1], v[3], v[5]]])
        elif name == "translate":
            T[0, 2] = v[0]
            T[1, 2] = v[1] if len(v) > 1 else 0.0
        elif name == "scale":
            T[0, 0] = v[0]
            T[1, 1] = v[1] if len(v) > 1 else v[0]
        elif name == "rotate":
            a = np.deg2rad(v[0])
            c, s = np.cos(a), np.sin(a)
            R = np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])
            if len(v) == 3:
                pre = np.eye(3)
                pre[0, 2], pre[1, 2] = v[1], v[2]
                post = np.eye(3)
                post[0, 2], post[1, 2] = -v[1], -v[2]
                R = pre @ R @ post
            T = R
        elif name == "skewX":
            T[0, 1] = np.tan(np.deg2rad(v[0]))
        elif name == "skewY":
            T[1, 0] = np.tan(np.deg2rad(v[0]))
        M = M @ T
    return M


def apply_transform(M: np.ndarray, points: np.ndarray) -> np.ndarray:
    pts = np.asarray(points, dtype=float)
    return pts @ M[:2, :2].T + M[:2, 2]
