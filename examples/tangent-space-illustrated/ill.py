"""Illustrated look for the tangent-space lecture — in the spirit of Keenan
Crane's figures, with our own touch.

The recipe: an **opaque, softly lit surface** (a fine quad mesh, shading
quantised into gentle bands) with a **crisp silhouette**, a **soft contact
shadow** instead of a ground plane, and everything drawn on top of it —
curves, arrows, dots — **haloed in paper white** so it separates cleanly from
the mesh behind. Curves on the surface are **occluded** by it: they stop at
the horizon instead of showing through. Labels are LaTeX in ink.

The geometry (exp/log maps on a sphere of radius R) is the same as in
examples/tangent-space/dome.py.
"""
import numpy as np
from lemur.anim import VShape, VGroup, Circle, MathTex
from lemur.anim import bezier as bz

R = 2.0

# paper, ink and a small, saturated accent palette
PAPER, INK = "#fbf9f4", "#2b2d42"
SHADE_DARK, SHADE_LIGHT = "#6f8db0", "#f3f7fb"
ORANGE, RED, BLUE, GREEN, PURPLE = "#ef7d2d", "#d8433c", "#2c69b0", "#3b9a66", "#7c5ea8"
PLANE_FILL, PLANE_EDGE = "#fde7c4", "#e39a4a"
LIGHT = (-0.55, -0.85, 1.1)              # key light: upper left, toward the default camera


# -- geometry (as in the plain version) ------------------------------------------

def unit(v):
    v = np.asarray(v, dtype=float)
    return v / (np.linalg.norm(v) or 1.0)


def S(theta, phi):
    return R * np.array([np.sin(theta) * np.cos(phi), np.sin(theta) * np.sin(phi), np.cos(theta)])


class Point:
    def __init__(self, theta, phi):
        self.p = S(theta, phi)
        self.n = unit(self.p)
        self.e1 = np.array([np.cos(theta) * np.cos(phi), np.cos(theta) * np.sin(phi), -np.sin(theta)])
        self.e2 = np.array([-np.sin(phi), np.cos(phi), 0.0])

    def dir(self, angle):
        return np.cos(angle) * self.e1 + np.sin(angle) * self.e2

    def exp(self, v):
        v = np.asarray(v, dtype=float)
        r = np.linalg.norm(v)
        if r < 1e-12:
            return self.p.copy()
        return R * (np.cos(r / R) * self.n + np.sin(r / R) * v / r)

    def plane_point(self, v):
        return self.p + np.asarray(v, dtype=float)

    def square(self, half=1.6):
        a, b = self.e1 * half, self.e2 * half
        return [self.p + a + b, self.p - a + b, self.p - a - b, self.p + a - b]


def blended(pt: Point, vecs, lam):
    lv = lam.get_value() if hasattr(lam, "get_value") else float(lam)
    return [(1 - lv) * pt.exp(v) + lv * pt.plane_point(v) for v in vecs]


# -- visibility -------------------------------------------------------------------

def occluded(view, X) -> bool:
    """Is the 3-D point ``X`` hidden behind the dome, seen from the camera? (A ray
    from X toward the camera that re-enters the upper hemisphere.)"""
    c = view.toward_camera()
    X = np.asarray(X, dtype=float)
    b = X @ c
    disc = b * b - (X @ X - R * R)
    if disc <= 0:
        return False
    rt = np.sqrt(disc)
    for s in (-b - rt, -b + rt):
        if s > 1e-3 * R and (X + s * c)[2] >= -1e-6:
            return True
    return False


DOME = {"c": [0.0, 0.0, 0.0], "R": R, "cap": 0.0}   # the occluder, for the deck's player


def _occ(view):
    """Tell the view what hides things: the player splits curves into their
    visible and hidden runs, and hides dots, against it — every frame."""
    if view.occluder is None:
        view.occluder = DOME
    return view


# -- the surface --------------------------------------------------------------

WARM = ((0.9, 0.7, 0.15), "#f6c89a", 0.32)   # our touch: a warm fill light from the back right


def dome(view, nu=40, nv=10):
    """The shaded dome: a fine quad mesh lit by a cool key light and a warm fill,
    back faces culled (the dome is convex, so that is all the occlusion it
    needs), over a coarse unculled copy that fills the slivers culling leaves
    along the silhouette."""
    def fn(u, v):
        return S(v, u)

    _occ(view)
    shade = dict(light=LIGHT, colors=(SHADE_DARK, SHADE_LIGHT), ambient=0.3, flip=True, fill_light=WARM)
    under = view.shaded_surface(fn, (0.0, 2 * np.pi), (0.0, np.pi / 2), nu=16, nv=4, cull=False,
                                mesh=None, mesh_width=1.2, **shade)
    top = view.shaded_surface(fn, (0.0, 2 * np.pi), (0.0, np.pi / 2), nu=nu, nv=nv,
                              mesh=0.06, mesh_width=0.7, **shade)
    for m in under.family:
        m.set_z_index(-1)                    # always beneath the fine mesh (and above the shadow)
    return VGroup(under, top)


def silhouette(view, color=INK, width=2.6):
    """The dome's outline for the current view: the upper half of the limb (the
    great circle facing the camera edge-on) and the front half of its base."""
    from lemur.anim import world as W

    _occ(view)

    def outline(kind):                        # drawn by the player for the current view
        m = VShape(color=color, stroke_width=width)
        fn = W.limb if kind == "limb" else W.base
        m.add_updater(lambda mm: mm.set_subpaths(
            [bz.line_handles(W.project(W.camera_of(view), fn(view.occluder, W.camera_of(view))))], [False]))
        m.world = W.World(view, kind)
        return view._tag(m)

    return VGroup(outline("limb"), outline("base"))


def shadow(view, rings=6):
    """A soft contact shadow: stacked, slightly larger translucent ellipses."""
    g = VGroup()
    for k in range(rings):
        r = R * (1.02 + 0.07 * k)
        pts = [(r * np.cos(f), r * np.sin(f), 0.0) for f in np.linspace(0, 2 * np.pi, 72, endpoint=False)]
        g.add(view.polygon(pts, fill_color=INK, fill_opacity=0.045, stroke_width=0))
    for m in g.family:
        m.set_z_index(-2)
    return g


# -- things drawn over the surface ---------------------------------------------

HIDDEN_DASH = (0.13, 0.09)          # world units: the dash pattern of hidden lines
HIDDEN_ALPHA = 0.7


def curve(view, points_fn, color=BLUE, width=4.0, closed=False, halo=True, occlude=True,
          hidden="dashed", ghost=None):
    """A curve through 3-D points (recomputed each frame), with a paper-white
    halo. With ``occlude``, the part behind the dome is drawn the way technical
    illustrations draw hidden lines — thin, dashed and faint (``hidden=None``
    drops it instead)."""
    _occ(view)

    def shape(col, w, part, dash=None, alpha=1.0):
        rule = ("vis" if part == "visible" else "hid") if occlude else None
        m = view.curve_fn(points_fn, closed=closed, rule=rule, ghost=ghost, color=col, stroke_width=w, dash=dash)
        m.set_stroke(opacity=alpha)
        return m

    parts = []
    if occlude and hidden:
        parts.append(shape(color, max(1.8, width * 0.6), "hidden", HIDDEN_DASH, HIDDEN_ALPHA))
    if halo:
        parts.append(shape(PAPER, width + 5.0, "visible"))
    parts.append(shape(color, width, "visible"))
    return VGroup(*parts)


def dot(view, where, color=ORANGE, radius=0.085):
    """A dot with a white ring; it hides when the dome is in the way."""
    d = Circle(radius=radius, fill_color=color, fill_opacity=1.0, stroke_color=PAPER, stroke_width=3.0)
    return _occ(view).pin(d, where, rule="hide")


def label(view, tex, where, offset=(0.0, 0.0), color=INK, scale=1.6):
    return view.pin(MathTex(tex, color=color).scale(scale), where, offset=offset)


def _ghost(view, m, anchor, alpha=0.3):
    """Dim ``m`` while ``anchor()`` is behind the dome (a view-dependent factor
    that animations never touch, so fades still work)."""
    if anchor is not None:
        m.view_alpha = alpha if occluded(view, anchor()) else 1.0


def arrow(view, state, color=RED, width=4.5, head=0.26, hw=0.13, halo=True, ghost=True):
    """A fat vector with a filled head, on a paper-white halo; drawn faint while
    its base point is behind the dome."""
    def make(col, extra):
        m = VShape(color=col, stroke_width=width + extra, fill_color=col, fill_opacity=1.0)

        def upd(_):
            P, V = state()
            if ghost:
                _ghost(view, m, lambda: P)
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

    return VGroup(*([make(PAPER, 5.0)] if halo else []), make(color, 0.0))


def tangent_plane(view, points_fn, grid=4, alpha=0.62, anchor=None):
    """The tangent plane as a sheet of paper: a warm translucent quad, a fine
    grid, and an outline. ``points_fn()`` gives its four corners (3-D); with an
    ``anchor()`` (its point of contact) it turns faint while that is hidden."""
    g = VGroup()

    def corners():
        return [np.asarray(p, float) for p in points_fn()]

    g.add(_occ(view).curve_fn(corners, closed=True, ghost=anchor, fill_color=PLANE_FILL, fill_opacity=alpha,
                              stroke_color=PLANE_EDGE, stroke_width=2.0))
    for k in range(1, grid):
        t = k / grid

        def across(t=t):                      # parallel to the edge c0 → c1
            c = corners()
            return [c[0] + t * (c[3] - c[0]), c[1] + t * (c[2] - c[1])]

        def along(t=t):                       # parallel to the edge c0 → c3
            c = corners()
            return [c[0] + t * (c[1] - c[0]), c[3] + t * (c[2] - c[3])]

        for fn in (across, along):
            g.add(curve(view, fn, color=PLANE_EDGE, width=0.9, halo=False, occlude=False, ghost=anchor))
    return g
