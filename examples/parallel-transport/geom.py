"""Shared geometry for the parallel-transport lecture: rotations, great-circle
arcs, parallel transport on the sphere, a wireframe sphere, and an arrow that
re-projects with the view."""
import numpy as np
from lemur.anim import VShape, VGroup
from lemur.anim import bezier as bz


def norm(v):
    v = np.asarray(v, dtype=float)
    return v / (np.linalg.norm(v) or 1.0)


def rot(axis, ang):
    """Rodrigues rotation matrix about ``axis`` by ``ang``."""
    a = norm(axis)
    c, s = np.cos(ang), np.sin(ang)
    K = np.array([[0, -a[2], a[1]], [a[2], 0, -a[0]], [-a[1], a[0], 0]])
    return np.eye(3) * c + s * K + (1 - c) * np.outer(a, a)


def arc(p, q, n=48):
    """Great-circle points from unit ``p`` to unit ``q``."""
    p, q = norm(p), norm(q)
    ang = np.arccos(np.clip(p @ q, -1, 1))
    ax = norm(np.cross(p, q))
    return np.array([rot(ax, ang * t) @ p for t in np.linspace(0, 1, n)])


def transport_along(V, pts):
    """Parallel-transport ``V`` along the polyline of unit points (each step a
    geodesic rotation). Returns the transported vector at every point."""
    out = [np.asarray(V, dtype=float)]
    for i in range(1, len(pts)):
        p, q = norm(pts[i - 1]), norm(pts[i])
        ax = np.cross(p, q)
        n = np.linalg.norm(ax)
        V = out[-1]
        if n > 1e-12:
            V = rot(ax / n, np.arccos(np.clip(p @ q, -1, 1))) @ V
        out.append(V)
    return np.array(out)


def tangent_basis(p):
    """An orthonormal basis of the tangent plane at unit point ``p``."""
    p = norm(p)
    e1 = np.cross(p, [0, 0, 1.0])
    if np.linalg.norm(e1) < 1e-6:
        e1 = np.cross(p, [0, 1.0, 0])
    e1 = norm(e1)
    return e1, np.cross(p, e1)


def sphere(view, lat=8, lon=14, samples=60, **style):
    """A wireframe unit sphere (meridians + latitude circles)."""
    style.setdefault("color", "#cdd3d9")
    style.setdefault("stroke_width", 1.0)

    def S(u, v):
        return (np.sin(v) * np.cos(u), np.sin(v) * np.sin(u), np.cos(v))

    g = VGroup()
    for u in np.linspace(0, 2 * np.pi, lon, endpoint=False):
        g.add(view.parametric(lambda v, u=u: S(u, v), 0, np.pi, samples, **style))
    for v in np.linspace(0, np.pi, lat + 2)[1:-1]:
        g.add(view.parametric(lambda u, v=v: S(u, v), 0, 2 * np.pi, samples, closed=True, **style))
    return g


def vector(view, state, color="#c0392b", scale=0.6, width=4.0, head=0.16, hw=0.09):
    """An updater-driven arrow; ``state()`` → ``(base_point3d, vec3d)``."""
    m = VShape(color=color, stroke_width=width)

    def upd(_):
        P, V = state()
        b = view.project(P)
        t = view.project(np.asarray(P, float) + np.asarray(V, float) * scale)
        d = t - b
        n = np.hypot(*d) or 1.0
        d = d / n
        perp = np.array([-d[1], d[0]])
        m.set_subpaths([bz.line_handles(np.array([b, t])),
                        bz.line_handles(np.array([t - d * head + perp * hw, t, t - d * head - perp * hw]))],
                       [False, False])

    m.add_updater(upd)
    return m
