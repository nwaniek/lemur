"""illustrate — paper-figure drawing for 3-D animations.

The look of the figures in a geometry paper (think Keenan Crane's notes): an
**opaque, softly lit surface** with a faint mesh, a **crisp silhouette**, a
**soft contact shadow**, and everything drawn over it — curves, vectors, dots —
on a **paper-white halo**. What is behind the surface is drawn the way
technical illustrations draw hidden lines: thin, dashed and faint; dots behind
it disappear, vectors and sheets fade to a ghost.

A :class:`Figure` bundles a :class:`~lemur.anim.View` (the camera) with an
*occluder* — the solid that hides things (a :class:`Sphere`, optionally cut to a
dome) — and a :class:`Palette`::

    from lemur.anim import Anim, View, Create
    from lemur.anim.illustrate import Figure, Sphere

    class Demo(Anim):
        def build(self):
            fig = Figure(View(azim=-30, elev=22, scale=1.8), Sphere(2.0))
            self.add(*fig.backdrop())                 # shadow, lit sphere, outline
            ring = fig.curve(lambda: [...3-D points...], color=fig.pal.blue)
            self.play(*[Create(m) for m in ring])

The shapes are *world shapes* (:mod:`lemur.anim.world`): they ship their 3-D
geometry and a rule, and the deck's player projects them, splits curves into
their visible and hidden runs, hides or ghosts dots — every frame, for the
current camera. So the camera can orbit while things move, and a still mesh
costs one keyframe however long the orbit. Visibility never touches opacity
(which animations own): the player applies its rules on top.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from . import bezier as bz
from .mobject import VGroup, VShape
from .shapes import Circle
from .world import World

__all__ = ["Palette", "PAPER", "NIGHT", "Sphere", "Torus", "Figure", "unit", "slerp"]


def unit(v):
    v = np.asarray(v, dtype=float)
    return v / (np.linalg.norm(v) or 1.0)


def slerp(a, b, t, radius: "float | None" = None):
    """The point a fraction ``t`` of the way from ``a`` to ``b`` along the great
    circle through them (a geodesic of the sphere of ``radius``, by default the
    length of ``a``)."""
    a, b = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    r = float(np.linalg.norm(a)) if radius is None else radius
    ua, ub = unit(a), unit(b)
    om = np.arccos(np.clip(ua @ ub, -1.0, 1.0))
    if om < 1e-9:
        return r * ua
    return r * (np.sin((1 - t) * om) * ua + np.sin(t * om) * ub) / np.sin(om)


@dataclass
class Palette:
    """Colours of a figure: page, ink, the surface's shadow→lit ramp, a warm
    fill light, a translucent sheet, and a few saturated accents."""
    paper: str = "#fbf9f4"
    ink: str = "#2b2d42"
    shade_dark: str = "#6f8db0"
    shade_light: str = "#f3f7fb"
    fill_light: str = "#f6c89a"
    sheet_fill: str = "#fde7c4"
    sheet_edge: str = "#e39a4a"
    orange: str = "#ef7d2d"
    red: str = "#d8433c"
    blue: str = "#2c69b0"
    green: str = "#3b9a66"
    purple: str = "#7c5ea8"
    shadow: str = "#2b2d42"


PAPER = Palette()
NIGHT = Palette(paper="#0f1420", ink="#e6edf3", shade_dark="#1b2a44", shade_light="#7fa3c9",
                fill_light="#b48ee0", sheet_fill="#274060", sheet_edge="#58c4dd", orange="#ffb454",
                red="#ff6b6b", blue="#58c4dd", green="#83e6a0", purple="#c3a6ff", shadow="#000000")


class Sphere:
    """A solid sphere as an occluder (``cap_z``: only the part above that height,
    e.g. ``cap_z=0`` for a dome standing on the ground)."""

    def __init__(self, radius: float = 1.0, center=(0.0, 0.0, 0.0), cap_z: "float | None" = None):
        self.R = float(radius)
        self.c = np.asarray(center, dtype=float)
        self.cap_z = cap_z

    def occludes(self, view, X) -> bool:
        """Is the 3-D point ``X`` hidden, seen from the camera? (A ray from X
        toward the camera that enters the solid.)"""
        c = view.toward_camera()
        X = np.asarray(X, dtype=float) - self.c
        b = X @ c
        disc = b * b - (X @ X - self.R * self.R)
        if disc <= 0:
            return False
        rt = np.sqrt(disc)
        for s in (-b - rt, -b + rt):
            if s > 1e-3 * self.R:
                if self.cap_z is None or (X + s * c)[2] + self.c[2] >= self.cap_z - 1e-6:
                    return True
        return False

    def surface(self, u, v):
        """The parametrisation used for shading: ``u`` around, ``v`` down from the top."""
        return self.c + self.R * np.array([np.sin(v) * np.cos(u), np.sin(v) * np.sin(u), np.cos(v)])

    def v_max(self) -> float:
        if self.cap_z is None:
            return np.pi
        return float(np.arccos(np.clip((self.cap_z - self.c[2]) / self.R, -1.0, 1.0)))

    flip = True                          # the parametrisation's normals point inward

    def ranges(self):
        return (0.0, 2 * np.pi), (0.0, self.v_max())

    def analytic(self) -> dict:
        """The player's analytic occluder (SVG views)."""
        return {"c": [float(x) for x in self.c], "R": self.R,
                "cap": None if self.cap_z is None else float(self.cap_z)}

    def shadow_rings(self, rings: int):
        """``(centre, z, inner, outer)`` per shadow ring on the ground."""
        z = self.cap_z if self.cap_z is not None else self.c[2] - 1.08 * self.R
        r0 = self.R if self.cap_z is not None else 0.8 * self.R
        return [(self.c[:2], z, 0.0, r0 * (1.02 + 0.07 * k)) for k in range(rings)]


class Torus:
    """A solid torus as an occluder: tube radius ``r`` around a circle of radius
    ``R`` in the plane ``z = center[2]``. Its hidden-line and hiding tests use
    the drawn surface itself, so it needs a GPU view (``View(renderer="gpu")``)."""

    flip = False

    def __init__(self, R: float = 2.0, r: float = 0.75, center=(0.0, 0.0, 0.0)):
        self.R, self.r = float(R), float(r)
        self.c = np.asarray(center, dtype=float)
        self._mesh = None

    def surface(self, u, v):
        """``u`` around the axis, ``v`` around the tube (0 = the outer equator)."""
        return self.c + np.array([(self.R + self.r * np.cos(v)) * np.cos(u),
                                  (self.R + self.r * np.cos(v)) * np.sin(u), self.r * np.sin(v)])

    def ranges(self):
        return (0.0, 2 * np.pi), (0.0, 2 * np.pi)

    def analytic(self):
        return None

    def occludes(self, view, X) -> bool:
        """Is ``X`` hidden behind the torus, seen from the camera? (Tested against
        a fine mesh of it, the way the deck's player tests.)"""
        from . import world as W

        if self._mesh is None:
            nu, nv = 96, 48
            us = np.linspace(0, 2 * np.pi, nu + 1)
            vs = np.linspace(0, 2 * np.pi, nv + 1)
            P = np.array([self.surface(u, v) for u in us for v in vs])
            idx = lambda i, j: i * (nv + 1) + j                                  # noqa: E731
            faces = [[idx(i, j), idx(i + 1, j), idx(i + 1, j + 1), idx(i, j + 1)]
                     for i in range(nu) for j in range(nv)]
            self._mesh = {"meshes": [W.mesh_occluder(P, W.mesh_geo(P, faces))]}
        return bool(W.occluded_many(self._mesh, W.camera_of(view), np.asarray(X, dtype=float).reshape(1, 3))[0])

    def shadow_rings(self, rings: int):
        z = self.c[2] - 1.02 * self.r
        return [(self.c[:2], z, self.R - self.r * (0.85 + 0.12 * k), self.R + self.r * (0.85 + 0.12 * k))
                for k in range(rings)]


def _runs(flags, closed):
    n = len(flags)
    if all(flags) or not any(flags):
        return [(flags[0], list(range(n)) + ([0] if closed else []))]
    start = 0
    if closed:                                   # start at a change, so no run wraps
        start = next(i for i in range(n) if flags[i] != flags[i - 1])
    order = [(start + k) % n for k in range(n)] if closed else list(range(n))
    runs: list = []
    for i in order:
        if runs and runs[-1][0] == flags[i]:
            runs[-1][1].append(i)
        else:
            runs.append((flags[i], [i]))
    return runs


class Figure:
    """A camera, an occluder and a palette — and the drawing vocabulary."""

    hidden_dash = (0.13, 0.09)       # world units
    hidden_alpha = 0.7
    ghost_alpha = 0.3

    def __init__(self, view, occluder: "Sphere | None" = None, palette: Palette = PAPER,
                 light=(-0.55, -0.85, 1.1), warm=(0.9, 0.7, 0.15)):
        self.view = view
        self.occ = occluder
        self.pal = palette
        self._solid = None
        if occluder is not None:           # the player's hidden-line / hide / ghost rules use it
            an = occluder.analytic()
            if an is None and not getattr(view, "gpu", False):
                raise ValueError(f"a {type(occluder).__name__} hides things only in a GPU view: "
                                 f"View(..., renderer='gpu')")
            view.occluder = an             # a GPU view uses its drawn surfaces instead
        self.light = light
        self.warm = warm

    # -- visibility -------------------------------------------------------

    def hidden(self, X) -> bool:
        return self.occ is not None and self.occ.occludes(self.view, X)

    def split(self, pts, closed=False, slots=2):
        """A polyline's visible and hidden parts, each as exactly ``slots``
        subpaths of one fixed length (animations morph point lists, so the
        layout must never change between frames). Hidden runs borrow the
        neighbouring visible point at each end, so dashes meet the line; runs
        keep their slots in curve order (no swapping, no flicker)."""
        pts = [np.asarray(p, dtype=float) for p in pts]
        n = len(pts)
        flags = [not self.hidden(p) for p in pts]
        m = n + 1
        out: dict = {True: [], False: []}
        runs = _runs(flags, closed)
        for k, (vis, idx) in enumerate(runs):
            first = idx[0]
            if not vis and len(runs) > 1:
                if k > 0 or closed:
                    idx = [runs[k - 1][1][-1]] + idx
                if k + 1 < len(runs) or closed:
                    idx = idx + [runs[(k + 1) % len(runs)][1][0]]
            out[vis].append((first, [pts[i] for i in idx]))
        result = []
        for vis in (True, False):
            keep = sorted(out[vis], key=lambda r: len(r[1]), reverse=True)[:slots]
            rs = [r for _, r in sorted(keep, key=lambda r: r[0])]
            if not rs:
                result.append(None)
                continue
            subs = [(r + [r[-1]] * (m - len(r)))[:m] for r in rs]
            subs += [[rs[0][0]] * m for _ in range(slots - len(subs))]
            result.append(subs)
        return result[0], result[1]

    def _ghost(self, m, anchor):
        if anchor is not None:
            m.view_alpha = self.ghost_alpha if self.hidden(anchor()) else 1.0

    # -- the solid ----------------------------------------------------------

    def shaded(self, fn, u_range, v_range, nu=40, nv=10, flip=False, under=True, mesh=0.06,
               tint=None, tint_mix=0.6):
        """A lit, opaque surface: a fine culled quad mesh over a coarse unculled
        copy (which fills the slivers culling leaves at the silhouette)."""
        v = self.view
        pal = self.pal
        shade = dict(light=self.light, colors=(pal.shade_dark, pal.shade_light), ambient=0.3,
                     flip=flip, fill_light=(self.warm, pal.fill_light, 0.32) if self.warm else None,
                     tint=tint, tint_mix=tint_mix)
        top = v.shaded_surface(fn, u_range, v_range, nu=nu, nv=nv, mesh=mesh, mesh_width=0.7, **shade)
        if not under or getattr(v, "gpu", False):          # a depth buffer needs no filler
            return VGroup(top)
        low = v.shaded_surface(fn, u_range, v_range, nu=max(nu // 3, 8), nv=max(nv // 3, 3), cull=False,
                               mesh=None, mesh_width=1.2, **shade)
        for m in low.family:
            m.set_z_index(-1)
        return VGroup(low, top)

    def solid(self, nu=40, nv=None, tint=None, tint_mix=0.6):
        """The occluder itself, shaded (a sphere, a dome, a torus); ``tint(u, v)``
        colours it by a function of its parameters (see ``View.shaded_surface``)."""
        s = self.occ
        ur, vr = s.ranges()
        nv = nv or max(4, int(round(nu * (vr[1] - vr[0]) / (ur[1] - ur[0]))))
        g = self.shaded(lambda u, w: s.surface(u, w), ur, vr, nu=nu, nv=nv, flip=s.flip,
                        tint=tint, tint_mix=tint_mix)
        if getattr(self.view, "gpu", False):
            self._solid = g.submobjects[-1]
        return g

    def silhouette(self, width=2.6):
        """The occluder's outline for the current view: the limb (the great circle
        seen edge-on) — for a dome its upper half plus the front of the base. In a
        GPU view, the smooth outline of the drawn solid (call ``solid`` first)."""
        s, view = self.occ, self.view
        if getattr(view, "gpu", False):
            if self._solid is None:
                raise ValueError("Figure.silhouette in a GPU view outlines the solid: call solid() first "
                                 "(backdrop() does both)")
            return VGroup(view.contour(self._solid, color=self.pal.ink, width=width))

        def limb():
            c = view.toward_camera()
            u = unit(np.cross(c, [0.0, 0.0, 1.0]))
            w = np.cross(c, u)
            w = w if w[2] >= 0 else -w
            span = np.pi if s.cap_z is not None else 2 * np.pi
            return [s.c + s.R * (np.cos(t) * u + np.sin(t) * w) for t in np.linspace(0, span, 90)]

        parts = [self._outline("limb", limb, width)]
        if s.cap_z is not None:
            rb = np.sqrt(max(s.R ** 2 - (s.cap_z - s.c[2]) ** 2, 0.0))

            def base():
                c = view.toward_camera()
                f = np.arctan2(c[1], c[0])
                return [np.array([s.c[0] + rb * np.cos(f + t), s.c[1] + rb * np.sin(f + t), s.cap_z])
                        for t in np.linspace(-np.pi / 2, np.pi / 2, 60)]

            parts.append(self._outline("base", base, width))
        return VGroup(*parts)

    def _outline(self, kind, points_fn, width):
        m = VShape(color=self.pal.ink, stroke_width=width)
        m.add_updater(lambda mm: mm.set_subpaths(
            [bz.line_handles(np.array([self.view.project(p) for p in points_fn()]))], [False]))
        m.world = World(self.view, kind)          # the player draws it for the current view
        return self.view._tag(m)

    def shadow(self, rings=6, z=None, radius=None, alpha=0.045):
        """A soft contact shadow: stacked, slightly larger translucent discs on
        the ground (``z``, default: under the occluder)."""
        s = self.occ
        if getattr(self.view, "gpu", False):
            return self._gpu_shadow(rings, z, alpha)
        z = (s.cap_z if s.cap_z is not None else s.c[2] - 1.08 * s.R) if z is None else z
        r0 = (radius or (s.R if s.cap_z is not None else 0.8 * s.R))
        g = VGroup()
        for k in range(rings):
            r = r0 * (1.02 + 0.07 * k)
            pts = [(s.c[0] + r * np.cos(f), s.c[1] + r * np.sin(f), z)
                   for f in np.linspace(0, 2 * np.pi, 72, endpoint=False)]
            g.add(self.view.polygon(pts, fill_color=self.pal.shadow, fill_opacity=alpha, stroke_width=0))
        for m in g.family:
            m.set_z_index(-2)
        return g

    def _gpu_shadow(self, rings, z, alpha):
        """The contact shadow as translucent rings (a torus casts an annulus)."""
        g = VGroup()
        n = 72
        for (cx, cy), z0, inner, outer in self.occ.shadow_rings(rings):
            zz = z0 if z is None else z
            ang = np.linspace(0, 2 * np.pi, n, endpoint=False)
            P = np.array([[cx + rr * np.cos(a), cy + rr * np.sin(a), zz] for rr in (inner, outer) for a in ang])
            faces = [[i, (i + 1) % n, n + (i + 1) % n, n + i] for i in range(n)]
            m = self.view.mesh(P, faces, self.pal.shadow, cull=False, occlude=False, fill_opacity=alpha)
            m.set_z_index(-2)
            g.add(m)
        return g

    def backdrop(self, nu=40):
        """``(shadow, solid, silhouette)`` — add them first."""
        return self.shadow(), self.solid(nu=nu), self.silhouette()

    # -- things drawn over it ------------------------------------------------

    def curve(self, points_fn, color=None, width=4.0, closed=False, halo=True, occlude=True,
              hidden="dashed", alpha=1.0, ghost=None):
        """A curve through 3-D points (``points_fn()`` is re-evaluated each frame),
        haloed; with ``occlude`` its hidden part is dashed (``hidden=None``: dropped);
        ``ghost`` (a 3-D point callable): faint while that point is hidden."""
        view, color = self.view, color or self.pal.blue

        def shape(col, w, part, dash=None, a=1.0):
            # the player splits it into its visible / hidden runs every frame
            rule = None if not (occlude and self.occ is not None) else ("vis" if part == "visible" else "hid")
            m = view.curve_fn(points_fn, closed=closed, rule=rule, ghost=ghost, ghost_alpha=self.ghost_alpha,
                              color=col, stroke_width=w, dash=dash)
            m.set_stroke(opacity=a)
            return m

        parts = []
        if occlude and hidden:
            parts.append(shape(color, max(1.8, width * 0.6), "hidden", self.hidden_dash, self.hidden_alpha * alpha))
        if halo:
            parts.append(shape(self.pal.paper, width + 5.0, "visible", a=alpha))
        parts.append(shape(color, width, "visible", a=alpha))
        return VGroup(*parts)

    def dot(self, where, color=None, radius=0.085, rim=3.0, ghost=False):
        """A dot with a paper rim, pinned to a 3-D point (or ``where()``); it hides
        behind the occluder (``ghost=True``: it fades instead)."""
        view, color = self.view, color or self.pal.orange
        at = where if callable(where) else (lambda w=np.asarray(where, float): w)
        d = Circle(radius=radius, fill_color=color, fill_opacity=1.0, stroke_color=self.pal.paper,
                   stroke_width=rim)
        return view.pin(d, at, rule="ghost" if ghost else "hide", ghost_alpha=self.ghost_alpha)

    def label(self, tex, where, offset=(0.0, 0.0), color=None, scale=1.6):
        from .text import MathTex

        view = self.view
        at = where if callable(where) else (lambda w=np.asarray(where, float): w)
        off = np.asarray(offset, dtype=float)
        m = MathTex(tex, color=color or self.pal.ink).scale(scale)
        return view.pin(m, at, offset=off)

    def arrow(self, state, color=None, width=4.5, head=0.26, hw=0.13, halo=True, ghost=True):
        """A fat vector from ``state()[0]`` along ``state()[1]``, on a halo; faint
        while its base is hidden."""
        view, color = self.view, color or self.pal.red

        def make(col, extra):
            m = VShape(color=col, stroke_width=width + extra, fill_color=col, fill_opacity=1.0)

            def upd(_):
                P, V = state()
                if ghost:
                    self._ghost(m, lambda: P)
                b = view.project(P)
                t = view.project(np.asarray(P, float) + np.asarray(V, float))
                d = t - b
                n = np.hypot(*d)
                if n < 1e-6:
                    m.set_subpaths([bz.line_handles(np.array([b, b + 1e-4]))], [False])
                    return
                d = d / n
                h = min(head, 0.45 * n)
                k = h / head
                perp = np.array([-d[1], d[0]])
                m.set_subpaths([bz.line_handles(np.array([b, t - d * h * 0.7])),
                                bz.line_handles(np.array([t - d * h + perp * hw * k, t,
                                                          t - d * h - perp * hw * k, t - d * h + perp * hw * k]))],
                               [False, True])

            m.add_updater(upd)
            return view._tag(m)

        return VGroup(*([make(self.pal.paper, 5.0)] if halo else []), make(color, 0.0))

    def sheet(self, corners_fn, grid=4, alpha=0.62, anchor=None):
        """A translucent sheet (a tangent plane, say) with a fine grid; faint while
        ``anchor()`` is hidden."""
        view, pal = self.view, self.pal
        g = VGroup()

        def corners():
            return [np.asarray(p, float) for p in corners_fn()]

        g.add(view.curve_fn(corners, closed=True, ghost=anchor, ghost_alpha=self.ghost_alpha,
                            fill_color=pal.sheet_fill, fill_opacity=alpha, stroke_color=pal.sheet_edge,
                            stroke_width=2.0))
        for k in range(1, grid):
            t = k / grid

            def across(t=t):
                c = corners()
                return [c[0] + t * (c[3] - c[0]), c[1] + t * (c[2] - c[1])]

            def along(t=t):
                c = corners()
                return [c[0] + t * (c[1] - c[0]), c[3] + t * (c[2] - c[3])]

            for fn in (across, along):
                g.add(self.curve(fn, color=pal.sheet_edge, width=0.9, halo=False, occlude=False, ghost=anchor))
        return g
