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
* ``mesh``   — a surface of flat faces (quads or triangles) with a colour each:
  it hides what is behind it. Views drawn by the GPU renderer
  (``View(renderer="gpu")``) use their opaque meshes as the occluder, for any
  shape — not only a sphere.
* ``contour`` — a mesh's outline for the current view: its smooth silhouette
  (where the surface turns away) and its open boundary, the hidden parts left out.

Hidden parts are found the way a depth buffer would find them, but exactly: a
point is hidden when an occluding triangle covers it on screen and lies nearer
to the camera (by more than a small tolerance, so a curve drawn *on* a surface
stays visible). The still frame of a GPU view is painter-sorted faces with the
visible parts of its lines on top — vector output for print and PDF.

A ``ghost`` anchor on any kind dims the shape to ``ghost_alpha`` while that
point is hidden. Keep this file and ``assets/svg/runtime.js`` (``LMRW``) in step.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

import numpy as np

__all__ = ["World", "Camera", "camera_of", "project", "toward", "occludes", "occluded_many", "runs",
           "split_polylines", "limb", "base", "bake_paths", "depth", "eye_dirs", "MeshGeo", "mesh_geo",
           "vertex_normals", "contour", "contour_occluder", "mesh_occluder", "painter_faces"]


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
    mesh: "dict | None" = None        # kind 'mesh': faces, colours, cull, edge, occlude
    source: object = None             # kind 'contour': the mesh shape it outlines


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
    """Is X hidden by the occluder ``{"c": centre, "R": radius, "cap": z|None}``
    (or, with ``{"meshes": …}``, by the occluding meshes of a GPU view)?"""
    if not occ:
        return False
    if occ.get("meshes") is not None:
        return bool(occluded_many(occ, cam, np.asarray(X, dtype=float).reshape(1, 3))[0])
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
    flags = [not h for h in occluded_many(occ, cam, np.asarray(pts, dtype=float))]
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


def occluded_many(occ, cam: Camera, P) -> np.ndarray:
    """``occludes`` for many points at once, (N,3) → bool (N,)."""
    P = np.asarray(P, dtype=float).reshape(-1, 3)
    if not occ:
        return np.zeros(len(P), dtype=bool)
    if occ.get("meshes") is None:
        return np.array([occludes(occ, cam, p) for p in P], dtype=bool)
    out = np.zeros(len(P), dtype=bool)
    if not len(P):
        return out
    xy = project(cam, P)
    d = depth(cam, P)
    for V, tris, eps in occ["meshes"]:
        V = np.asarray(V, dtype=float)
        a2, b2, c2 = (project(cam, V[tris[:, k]]) for k in range(3))
        dv = depth(cam, V)
        da, db, dc = dv[tris[:, 0]], dv[tris[:, 1]], dv[tris[:, 2]]
        area = (b2[:, 0] - a2[:, 0]) * (c2[:, 1] - a2[:, 1]) - (b2[:, 1] - a2[:, 1]) * (c2[:, 0] - a2[:, 0])
        ok = np.abs(area) > 1e-12
        a2, b2, c2, da, db, dc, area = a2[ok], b2[ok], c2[ok], da[ok], db[ok], dc[ok], area[ok]
        tol = 1e-9 * max(float(np.ptp(np.concatenate([a2, b2, c2]))), 1e-9)   # no cracks at seams
        lo = np.minimum(np.minimum(a2, b2), c2) - tol
        hi = np.maximum(np.maximum(a2, b2), c2) + tol
        for s0 in range(0, len(P), 256):
            q, dq = xy[s0:s0 + 256], d[s0:s0 + 256]
            inbox = ((q[:, None, 0] >= lo[None, :, 0]) & (q[:, None, 0] <= hi[None, :, 0])
                     & (q[:, None, 1] >= lo[None, :, 1]) & (q[:, None, 1] <= hi[None, :, 1]))
            pi, ti = np.nonzero(inbox)
            if not len(pi):
                continue
            p = q[pi]
            A, B, C = a2[ti], b2[ti], c2[ti]
            ar = area[ti]
            l1 = ((C[:, 0] - B[:, 0]) * (p[:, 1] - B[:, 1]) - (C[:, 1] - B[:, 1]) * (p[:, 0] - B[:, 0])) / ar
            l2 = ((A[:, 0] - C[:, 0]) * (p[:, 1] - C[:, 1]) - (A[:, 1] - C[:, 1]) * (p[:, 0] - C[:, 0])) / ar
            l3 = 1.0 - l1 - l2
            inside = (l1 >= -1e-9) & (l2 >= -1e-9) & (l3 >= -1e-9)
            zt = l1 * da[ti] + l2 * db[ti] + l3 * dc[ti]
            hid = inside & (zt > dq[pi] + eps)
            if hid.any():
                out[s0 + pi[hid]] = True
    return out


# -- meshes ---------------------------------------------------------------------------

#: How far (relative to a mesh's size) a point may lie behind the surface and
#: still count as *on* it: faces are flat chords of a curved surface, so a curve
#: drawn on the surface dips slightly below them.
MESH_EPS = 2e-2


def depth(cam: Camera, P) -> np.ndarray:
    """Depth toward the camera (larger = nearer), like ``View.depth``."""
    P = np.asarray(P, dtype=float) - np.asarray(cam.origin)
    return P @ toward(cam)


def eye_dirs(cam: Camera, P) -> np.ndarray:
    """Unit vectors from each point toward the camera (parallel for an
    orthographic view; toward the eye for a perspective one)."""
    P = np.asarray(P, dtype=float).reshape(-1, 3)
    t = toward(cam)
    if cam.persp is None:
        return np.broadcast_to(t, P.shape).copy()
    eye = np.asarray(cam.origin) + cam.persp * t
    d = eye - P
    return d / np.maximum(np.linalg.norm(d, axis=1, keepdims=True), 1e-12)


@dataclass
class MeshGeo:
    """A mesh's topology: faces (F,k), their triangles (fan), the vertices welded
    by position (seams of a closed surface share their vertices), and the
    triangles' welded edges."""
    faces: np.ndarray
    tris: np.ndarray
    ids: np.ndarray
    boundary: np.ndarray        # (B,2) vertex index pairs on the open boundary


def mesh_geo(P, faces) -> MeshGeo:
    P = np.asarray(P, dtype=float).reshape(-1, 3)
    faces = np.asarray(faces, dtype=np.int64)
    k = faces.shape[1]
    tris = np.concatenate([faces[:, [0, j, j + 1]] for j in range(1, k - 1)])
    scale = max(float(np.abs(P).max()) if len(P) else 1.0, 1e-9)
    _u, ids = np.unique(np.round(P / scale, 7), axis=0, return_inverse=True)
    ids = ids.reshape(-1)
    # boundary: welded face edges used by one face only
    e = np.concatenate([faces[:, [j, (j + 1) % k]] for j in range(k)])
    we = np.sort(ids[e], axis=1)
    _k, first, counts = np.unique(we, axis=0, return_index=True, return_counts=True)
    bnd = e[first[counts == 1]]
    bnd = bnd[ids[bnd[:, 0]] != ids[bnd[:, 1]]]            # not a collapsed (pole) edge
    return MeshGeo(faces, tris, ids, bnd)


def face_normals(P, faces) -> np.ndarray:
    """(Unnormalised) face normals, following the vertex order: for a quad the
    cross product of its diagonals, for a triangle of two edges."""
    P = np.asarray(P, dtype=float)
    f = np.asarray(faces)
    if f.shape[1] >= 4:
        n = np.cross(P[f[:, 2]] - P[f[:, 0]], P[f[:, 3]] - P[f[:, 1]])
        small = np.linalg.norm(n, axis=1) < 1e-12
        if small.any():
            n[small] = np.cross(P[f[small, 1]] - P[f[small, 0]], P[f[small, 3]] - P[f[small, 0]])
        return n
    return np.cross(P[f[:, 1]] - P[f[:, 0]], P[f[:, 2]] - P[f[:, 0]])


def vertex_normals(P, geo: MeshGeo) -> np.ndarray:
    """Smooth normals: the triangles' area-weighted normals summed over each
    welded vertex."""
    P = np.asarray(P, dtype=float)
    t = geo.tris
    n = np.cross(P[t[:, 1]] - P[t[:, 0]], P[t[:, 2]] - P[t[:, 0]])
    acc = np.zeros((geo.ids.max() + 1 if len(geo.ids) else 0, 3))
    for j in range(3):
        np.add.at(acc, geo.ids[t[:, j]], n)
    vn = acc[geo.ids]
    return vn / np.maximum(np.linalg.norm(vn, axis=1, keepdims=True), 1e-12)


def contour(cam: Camera, P, geo: MeshGeo, normals=None) -> list:
    """The mesh's outline for ``cam`` as 3-D polylines: the smooth silhouette —
    where ``normal · (toward camera)`` changes sign, interpolated along the
    triangles' edges, so it is a smooth curve rather than a staircase of mesh
    edges — and the open boundary. Hidden parts are *not* removed here."""
    P = np.asarray(P, dtype=float)
    vn = vertex_normals(P, geo) if normals is None else normals
    f = np.einsum("ij,ij->i", vn, eye_dirs(cam, P))
    ids = geo.ids
    pos = f >= 0.0
    seg_keys: list = []
    points: dict = {}
    for t in geo.tris:
        cross = []
        for a, b in ((t[0], t[1]), (t[1], t[2]), (t[2], t[0])):
            if pos[a] != pos[b] and ids[a] != ids[b]:
                key = (min(ids[a], ids[b]), max(ids[a], ids[b]))
                if key not in points:
                    w = f[a] / (f[a] - f[b])
                    points[key] = P[a] + w * (P[b] - P[a])
                cross.append(key)
        if len(cross) == 2:
            seg_keys.append((cross[0], cross[1]))
    for a, b in geo.boundary:
        ka, kb = ("v", int(ids[a])), ("v", int(ids[b]))
        points.setdefault(ka, P[a])
        points.setdefault(kb, P[b])
        seg_keys.append((ka, kb))
    return [np.array([points[k] for k in chain]) for chain in _chain(seg_keys)]


def _chain(segs: list) -> list:
    """Join segments that share end points into polylines (lists of keys)."""
    adj: dict = {}
    for i, (a, b) in enumerate(segs):
        adj.setdefault(a, []).append(i)
        adj.setdefault(b, []).append(i)
    used = [False] * len(segs)
    out = []

    def walk(start_seg, start_key):
        keys = [start_key]
        cur_seg, cur = start_seg, start_key
        while True:
            used[cur_seg] = True
            a, b = segs[cur_seg]
            nxt = b if a == cur else a
            keys.append(nxt)
            cand = [j for j in adj[nxt] if not used[j]]
            if not cand:
                return keys
            cur_seg, cur = cand[0], nxt

    ends = [k for k, v in adj.items() if len(v) == 1]           # open chains start at an end
    for k in ends:
        for i in adj[k]:
            if not used[i]:
                out.append(walk(i, k))
    for i in range(len(segs)):                                    # then the closed loops
        if not used[i]:
            out.append(walk(i, segs[i][0]))
    return out


def mesh_occluder(P, geo: MeshGeo) -> tuple:
    """``(vertices, triangles, eps)`` for an occluder set ``{"meshes": [...]}``."""
    P = np.asarray(P, dtype=float)
    r = float(np.linalg.norm(P.max(axis=0) - P.min(axis=0))) / 2 if len(P) else 1.0
    return (P, geo.tris, MESH_EPS * max(r, 1e-9))


#: A silhouette point lies where its own surface turns away, at a grazing angle,
#: so neighbouring faces cover it slightly nearer than a curve on the surface
#: would see; its visibility test uses this many times the tolerance.
CONTOUR_EPS_SCALE = 4.0


def contour_occluder(occ):
    """``occ`` with the tolerance widened for testing silhouette points."""
    if not occ or occ.get("meshes") is None:
        return occ
    return {"meshes": [(V, t, eps * CONTOUR_EPS_SCALE) for V, t, eps in occ["meshes"]]}


def painter_faces(cam: Camera, P, geo: MeshGeo, cull: bool) -> list:
    """The faces to draw for ``cam``, far to near: ``[(face index, pts2d)]``;
    with ``cull``, faces turned away from the camera are left out."""
    P = np.asarray(P, dtype=float)
    f = geo.faces
    cen = P[f].mean(axis=1)
    keep = np.ones(len(f), dtype=bool)
    if cull:
        n = face_normals(P, f)
        keep = np.einsum("ij,ij->i", n, eye_dirs(cam, cen)) > 0.0
    d = depth(cam, cen)
    order = [i for i in np.argsort(d, kind="stable") if keep[i]]
    xy = project(cam, P)
    return [(int(i), xy[f[i]]) for i in order]
