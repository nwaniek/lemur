"""Shared geometry for the tangent-space deck: a dome (the upper half of a
sphere of radius R), a point p on it with its tangent plane, geodesics, and the
exponential / logarithm maps that translate between the two.

Everything is plain numpy in world coordinates (z up); the animations draw it
through a lemur.anim.View. Its shapes ship as 3-D geometry that the deck's
player projects each frame, so the camera can orbit while things move.
"""
import numpy as np
from lemur.anim import VShape, VGroup, MathTex
from lemur.anim import bezier as bz

R = 2.0                                    # the dome's radius

# a 3Blue1Brown-ish palette on the dark theme
BLUE, YELLOW, RED, GREEN, PURPLE = "#58c4dd", "#ffd166", "#fc6255", "#83c167", "#b48ee0"
WIRE, GROUND, INK = "#6b7f96", "#18212b", "#e6edf3"


def unit(v):
    v = np.asarray(v, dtype=float)
    return v / (np.linalg.norm(v) or 1.0)


def S(theta, phi):
    """A point on the dome: ``theta`` down from the top, ``phi`` around it."""
    return R * np.array([np.sin(theta) * np.cos(phi), np.sin(theta) * np.sin(phi), np.cos(theta)])


class Point:
    """A point p on the dome with its tangent-space machinery."""

    def __init__(self, theta, phi):
        self.p = S(theta, phi)
        self.n = unit(self.p)                                   # the normal
        # an orthonormal tangent frame: "downhill" and "around"
        self.e1 = np.array([np.cos(theta) * np.cos(phi), np.cos(theta) * np.sin(phi), -np.sin(theta)])
        self.e2 = np.array([-np.sin(phi), np.cos(phi), 0.0])

    def dir(self, angle):
        """The unit tangent vector at ``angle`` in the (e1, e2) frame."""
        return np.cos(angle) * self.e1 + np.sin(angle) * self.e2

    def exp(self, v):
        """exp_p(v): walk straight (along a great circle) for |v| units."""
        v = np.asarray(v, dtype=float)
        r = np.linalg.norm(v)
        if r < 1e-12:
            return self.p.copy()
        return R * (np.cos(r / R) * self.n + np.sin(r / R) * v / r)

    def log(self, q):
        """log_p(q): the tangent vector whose exp lands on q."""
        q = unit(q)
        c = np.clip(self.n @ q, -1.0, 1.0)
        t = q - c * self.n
        nt = np.linalg.norm(t)
        return np.zeros(3) if nt < 1e-12 else R * np.arccos(c) * t / nt

    def plane_point(self, v):
        """The tip of tangent vector ``v`` drawn in the plane touching at p."""
        return self.p + np.asarray(v, dtype=float)

    def square(self, half=1.6):
        a, b = self.e1 * half, self.e2 * half
        return [self.p + a + b, self.p - a + b, self.p - a - b, self.p + a - b]


def blended(pt: Point, vecs, lam):
    """Points that slide between the dome (``lam=0``: exp_p of each tangent
    vector) and the flat tangent plane (``lam=1``: p + v)."""
    lv = lam.get_value() if hasattr(lam, "get_value") else float(lam)
    return [(1 - lv) * pt.exp(v) + lv * pt.plane_point(v) for v in vecs]


# -- drawing helpers ----------------------------------------------------------

def dome(view, meridians=16, parallels=5, samples=40, **style):
    """A wireframe dome: meridians from the top down to the ground, parallels."""
    style.setdefault("color", WIRE)
    style.setdefault("stroke_width", 1.5)
    g = VGroup()
    for phi in np.linspace(0, 2 * np.pi, meridians, endpoint=False):
        g.add(view.parametric(lambda t, phi=phi: S(t, phi), 0.0, np.pi / 2, samples, **style))
    for th in np.linspace(0, np.pi / 2, parallels + 1)[1:]:
        g.add(view.parametric(lambda f, th=th: S(th, f), 0.0, 2 * np.pi, samples * 2, closed=True, **style))
    return g


def ground(view, radius=1.25 * R, **style):
    """A faint disc under the dome, so it reads as standing on something."""
    style.setdefault("fill_color", GROUND)
    style.setdefault("fill_opacity", 0.9)
    style.setdefault("stroke_width", 0)
    pts = [(radius * np.cos(f), radius * np.sin(f), 0.0) for f in np.linspace(0, 2 * np.pi, 72, endpoint=False)]
    disc = view.polygon(pts, **style)
    disc.set_z_index(-10)
    return disc


def moving_curve(view, points_fn, closed=False, **style):
    """A polyline whose 3-D points are recomputed every frame (``points_fn()``)."""
    return view.curve_fn(points_fn, closed=closed, **style)


def moving_polygon(view, points_fn, **style):
    style.setdefault("stroke_width", 1.5)
    return moving_curve(view, points_fn, closed=True, **style)


def dot(view, where, color=YELLOW, radius=0.075):
    """A dot pinned to a 3-D point, or to ``where()`` if it is a callable."""
    return view.dot(where, radius=radius, color=color)


def label(view, tex, where, offset=(0.0, 0.0), color=INK, scale=1.6):
    """Upright maths pinned next to a 3-D point (tracks it as things move)."""
    return view.pin(MathTex(tex, color=color).scale(scale), where, offset=offset)


def arrow(view, state, color=RED, width=4.0, head=0.2, hw=0.11):
    """An arrow from ``state()[0]`` along ``state()[1]`` (3-D), re-drawn per frame."""
    m = VShape(color=color, stroke_width=width)

    def upd(_):
        P, V = state()
        b = view.project(P)
        t = view.project(np.asarray(P, float) + np.asarray(V, float))
        d = t - b
        n = np.hypot(*d)
        if n < 1e-6:
            m.set_subpaths([bz.line_handles(np.array([b, b + 1e-4]))], [False])
            return
        d = d / n
        h = min(head, 0.45 * n)
        perp = np.array([-d[1], d[0]])
        m.set_subpaths([bz.line_handles(np.array([b, t - d * h * 0.6])),
                        bz.line_handles(np.array([t - d * h + perp * hw * h / head, t,
                                                  t - d * h - perp * hw * h / head, t - d * h + perp * hw * h / head]))],
                       [False, True])
        m.set_fill(color, 1.0)

    m.add_updater(upd)
    return view._tag(m)


def edge_on_azim(view_elev_deg, n, near_azim_deg):
    """The camera azimuth (degrees), closest to ``near_azim_deg``, that sees the
    plane with normal ``n`` exactly edge-on from elevation ``view_elev_deg``."""
    e = np.radians(view_elev_deg)
    a = np.radians(np.linspace(near_azim_deg - 180, near_azim_deg + 180, 7201))
    toward = np.stack([-np.sin(a) * np.cos(e), -np.cos(a) * np.cos(e), np.full_like(a, np.sin(e))], 1)
    s = np.abs(toward @ n)
    zero = np.where(s < s.min() + 1e-3)[0]            # the (two) edge-on directions
    return float(np.degrees(a[min(zero, key=lambda i: abs(a[i] - np.radians(near_azim_deg)))]))
