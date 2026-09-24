"""world — 3-D shapes that the *player* projects.

A shape made through a :class:`~lemur.anim.View` used to be re-projected to 2D
in Python on every frame, and the recorder stored those 2D points — so a static
mesh seen by an orbiting camera cost a keyframe per frame per shape. Instead, a
3-D shape now carries a :class:`World` spec: its geometry in world space and a
rule for how to draw it. The recorder stores the 3-D data (static geometry →
one keyframe, however the camera moves) plus one small camera track per view,
and the display runtime projects, culls, splits and places every frame. The
emitter's still frame (print, no-JS) is baked with the same maths, below.

Kinds:

* ``poly``   — polylines in 3-D. Rules: ``None`` (draw all), ``"cull"`` (hide
  when the face normal points away), ``"vis"`` / ``"hid"`` (only the part not
  hidden / only the part hidden by the view's occluder — hidden lines).
* ``anchor`` — the shape's own 2-D outline, placed at a projected 3-D point
  (dots, labels). Rules: ``"hide"`` / ``"ghost"`` when the point is hidden.
* ``limb`` / ``base`` — the occluding sphere's outline for the current view
  (and, for a dome, the front of its base).

A ``ghost`` anchor on any kind dims the shape to ``ghost_alpha`` while that
point is hidden. Keep this file and ``assets/svg/runtime.js`` (``LMRW``) in step.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

import numpy as np

__all__ = ["World", "Camera", "camera_of", "project", "toward", "occludes", "runs", "split_polylines",
           "limb", "base", "bake_paths"]


@dataclass
class World:
    view: object
    kind: str = "poly"
    points: "Callable[[], list] | None" = None       # poly: [(n,3) …]; anchor: (3,)
    closed: list = field(default_factory=list)
    rule: "str | None" = None
    normal: "np.ndarray | None" = None
    ghost: "Callable[[], np.ndarray] | None" = None
    ghost_alpha: float = 0.3


@dataclass
class Camera:
    """A view's projection at one moment."""
    azim: float
    elev: float
    scale: float
    center: tuple
    origin: tuple
    persp: "float | None"


def camera_of(view) -> Camera:
    return Camera(float(view.azim.get_value()), float(view.elev.get_value()), float(view.scale),
                  (float(view.center[0]), float(view.center[1])), tuple(float(v) for v in view._data_origin),
                  None if view._persp is None else float(view._persp))


def project(cam: Camera, P) -> np.ndarray:
    """Points (…,3) → animation-plane points (…,2). Mirrors ``View.project``."""
    P = np.asarray(P, dtype=float) - np.asarray(cam.origin)
    x, y, z = P[..., 0], P[..., 1], P[..., 2]
    ca, sa, se, ce = np.cos(cam.azim), np.sin(cam.azim), np.sin(cam.elev), np.cos(cam.elev)
    sx = ca * x - sa * y
    sy = (sa * x + ca * y) * se + z * ce
    if cam.persp is not None:
        dc = z * se - (sa * x + ca * y) * ce
        k = cam.persp / np.maximum(cam.persp - dc, 1e-3)
        sx, sy = sx * k, sy * k
    return np.stack([sx * cam.scale + cam.center[0], sy * cam.scale + cam.center[1]], axis=-1)


def toward(cam: Camera) -> np.ndarray:
    a, e = cam.azim, cam.elev
    return np.array([-np.sin(a) * np.cos(e), -np.cos(a) * np.cos(e), np.sin(e)])


#: A point this close to the occluder's surface (relative to its radius) counts
#: as on it, not behind it. Shipped points are rounded and interpolated (a moving
#: dot's track cuts chords a few thousandths *inside* the sphere), and an exact
#: test would hide things that sit on the surface.
SURFACE_EPS = 1e-2


def occludes(occ: "dict | None", cam: Camera, X) -> bool:
    """Is X hidden by the occluder ``{"c": centre, "R": radius, "cap": z|None}``?"""
    if not occ:
        return False
    c = toward(cam)
    X = np.asarray(X, dtype=float) - np.asarray(occ["c"], dtype=float)
    R = occ["R"]
    b = float(X @ c)
    disc = b * b - (float(X @ X) - R * R)
    if disc <= 0:
        return False
    rt = np.sqrt(disc)
    for s in (-b - rt, -b + rt):
        if s > SURFACE_EPS * R:
            cap = occ.get("cap")
            if cap is None or (X + s * c)[2] + occ["c"][2] >= cap - 1e-6:
                return True
    return False


def runs(flags, closed):
    """Maximal runs of equal flags as ``[(flag, [indices])]``; a closed curve's
    runs start at a change (none wraps), an all-equal ring repeats its start."""
    n = len(flags)
    if n == 0:
        return []
    if all(flags) or not any(flags):
        return [(bool(flags[0]), list(range(n)) + ([0] if closed else []))]
    start = next(i for i in range(n) if flags[i] != flags[i - 1]) if closed else 0
    out: list = []
    for k in range(n):
        i = (start + k) % n if closed else k
        if out and out[-1][0] == bool(flags[i]):
            out[-1][1].append(i)
        else:
            out.append((bool(flags[i]), [i]))
    return out


def split_polylines(occ, cam, pts, closed, want_visible: bool) -> list:
    """The visible (or hidden) runs of one 3-D polyline as index lists; hidden
    runs borrow the neighbouring visible point at each end so the dashes meet
    the solid line."""
    flags = [not occludes(occ, cam, p) for p in pts]
    rs = runs(flags, closed)
    out = []
    for k, (vis, idx) in enumerate(rs):
        if vis != want_visible:
            continue
        if not vis and len(rs) > 1:
            if k > 0 or closed:
                idx = [rs[k - 1][1][-1]] + idx
            if k + 1 < len(rs) or closed:
                idx = idx + [rs[(k + 1) % len(rs)][1][0]]
        if len(idx) >= 2:
            out.append(idx)
    return out


def limb(occ, cam, n: int = 90) -> np.ndarray:
    """The occluder's silhouette: the great circle seen edge-on (its upper half
    for a dome), as 3-D points."""
    c = toward(cam)
    u = np.cross(c, [0.0, 0.0, 1.0])
    u = u / (np.linalg.norm(u) or 1.0)
    w = np.cross(c, u)
    w = w if w[2] >= 0 else -w
    span = np.pi if occ.get("cap") is not None else 2 * np.pi
    t = np.linspace(0.0, span, n)
    return np.asarray(occ["c"]) + occ["R"] * (np.cos(t)[:, None] * u + np.sin(t)[:, None] * w)


def base(occ, cam, n: int = 60) -> np.ndarray:
    """A dome's base circle, the half facing the camera, as 3-D points."""
    c = toward(cam)
    cap = occ["cap"]
    rb = np.sqrt(max(occ["R"] ** 2 - (cap - occ["c"][2]) ** 2, 0.0))
    f = np.arctan2(c[1], c[0])
    t = np.linspace(-np.pi / 2, np.pi / 2, n) + f
    return np.stack([occ["c"][0] + rb * np.cos(t), occ["c"][1] + rb * np.sin(t), np.full(n, cap)], axis=1)


def bake_paths(kind, rule, occ, cam, polys, closed) -> "list[tuple[np.ndarray, bool]]":
    """The 2-D polylines ``[(pts2d, closed)]`` a world shape draws for ``cam``
    (the runtime does the same each frame)."""
    if kind == "limb":
        return [(project(cam, limb(occ, cam)), False)]
    if kind == "base":
        return [(project(cam, base(occ, cam)), False)]
    out = []
    for P, cl in zip(polys, closed):
        P = np.asarray(P, dtype=float)
        if rule in ("vis", "hid"):
            for idx in split_polylines(occ, cam, P, cl, rule == "vis"):
                out.append((project(cam, P[idx]), False))
        else:
            out.append((project(cam, P), cl))
    return out
