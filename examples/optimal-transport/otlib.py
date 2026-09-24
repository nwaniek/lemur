"""Optimal transport on a sphere, for the particle animations.

Measures are clouds of N equal-mass particles on the sphere of radius R. The
ground cost is the squared geodesic distance. The exact plan between two such
clouds is a permutation (Birkhoff: the vertices of the transport polytope), so
the discrete Monge map is a linear assignment problem; the entropic plan comes
from Sinkhorn (log domain). Particles then move along great circles — McCann's
displacement interpolation, which on a manifold follows geodesics.
"""
import numpy as np
from scipy.optimize import linear_sum_assignment
from scipy.special import logsumexp

from lemur.anim import View, ValueTracker
from lemur.anim.illustrate import Figure, Sphere, PAPER, slerp, unit
from lemur.anim.color import interpolate_color

R = 2.0
N = 180


def direction(lat, lon):
    la, lo = np.radians(lat), np.radians(lon)
    return np.array([np.cos(la) * np.cos(lo), np.cos(la) * np.sin(lo), np.sin(la)])


def frame(c):
    """An orthonormal tangent frame at the unit direction c."""
    c = unit(c)
    e1 = unit(np.cross([0.0, 0.0, 1.0], c)) if abs(c[2]) < 0.99 else np.array([1.0, 0.0, 0.0])
    return e1, np.cross(c, e1)


def exp(c, v):
    """exp_c(v) on the sphere of radius R (c a unit direction, v tangent, length in world units)."""
    c = unit(c)
    r = np.linalg.norm(v)
    if r < 1e-12:
        return R * c
    return R * (np.cos(r / R) * c + np.sin(r / R) * v / r)


def from_plane(c, xy):
    """Points given in the tangent plane at c (2-D coordinates) → the sphere."""
    e1, e2 = frame(c)
    return np.array([exp(c, x * e1 + y * e2) for x, y in xy])


# -- measures -------------------------------------------------------------------

def blob(c, sigma=0.32, n=N, seed=1):
    rng = np.random.default_rng(seed)
    return from_plane(c, rng.normal(0.0, sigma, (n, 2)))


def ring(c, radius=0.75, width=0.06, n=N, seed=2):
    rng = np.random.default_rng(seed)
    a = rng.uniform(0, 2 * np.pi, n)
    r = radius + rng.normal(0.0, width, n)
    return from_plane(c, np.c_[r * np.cos(a), r * np.sin(a)])


def two_blobs(c, sep=0.75, sigma=0.17, n=N, seed=3):
    rng = np.random.default_rng(seed)
    side = np.where(np.arange(n) % 2 == 0, -1.0, 1.0)
    xy = rng.normal(0.0, sigma, (n, 2)) + np.c_[side * sep, np.zeros(n)]
    return from_plane(c, xy)


def spiral(c, turns=1.6, n=N, seed=4):
    rng = np.random.default_rng(seed)
    s = np.sort(rng.uniform(0.05, 1.0, n))
    a = s * turns * 2 * np.pi
    r = 0.95 * s + rng.normal(0.0, 0.03, n)
    return from_plane(c, np.c_[r * np.cos(a), r * np.sin(a)])


def heart(c, n=N, seed=5):
    rng = np.random.default_rng(seed)
    t = rng.uniform(0, 2 * np.pi, n)
    x = 16 * np.sin(t) ** 3
    y = 13 * np.cos(t) - 5 * np.cos(2 * t) - 2 * np.cos(3 * t) - np.cos(4 * t)
    xy = np.c_[x, y] / 17.0 * 0.95 + rng.normal(0.0, 0.025, (n, 2))
    return from_plane(c, xy)


# -- transport ------------------------------------------------------------------

def cost(X, Y):
    """Squared geodesic distances on the sphere of radius R."""
    cos = np.clip((X @ Y.T) / (R * R), -1.0, 1.0)
    return (R * np.arccos(cos)) ** 2


def monge(X, Y):
    """The optimal assignment: X[i] goes to Y[perm[i]]."""
    _, perm = linear_sum_assignment(cost(X, Y))
    return perm


def total_cost(X, Y, perm):
    return float(np.mean(cost(X, Y)[np.arange(len(X)), perm]))


def sinkhorn(X, Y, eps, iters=600):
    """The entropic plan (uniform marginals), log-domain for small ``eps``."""
    C = cost(X, Y)
    n, m = C.shape
    la, lb = -np.log(n) * np.ones(n), -np.log(m) * np.ones(m)
    f, g = np.zeros(n), np.zeros(m)
    for _ in range(iters):
        f = eps * (la - logsumexp((g[None, :] - C) / eps, axis=1))
        g = eps * (lb - logsumexp((f[:, None] - C) / eps, axis=0))
    return np.exp((f[:, None] + g[None, :] - C) / eps)


def barycentric(P, Y):
    """Where each source particle goes on average under the plan P — the
    (extrinsic) barycentre, projected back onto the sphere."""
    B = (P / P.sum(axis=1, keepdims=True)) @ Y
    return np.array([R * unit(b) for b in B])


# -- drawing --------------------------------------------------------------------

CYCLE = ["#ef7d2d", "#d8433c", "#b8407e", "#7c5ea8", "#2c69b0", "#2a9d8f", "#3b9a66", "#c9a227"]


def cyclic(t):
    """A colour on a closed loop through CYCLE (t in [0, 1))."""
    t = (t % 1.0) * len(CYCLE)
    i = int(t)
    return interpolate_color(CYCLE[i], CYCLE[(i + 1) % len(CYCLE)], t - i).hexa()[:7]


def colours_by_angle(X, c):
    """Colour particles by their angle around c — so you can follow them."""
    e1, e2 = frame(c)
    return [cyclic((np.arctan2(x @ e2, x @ e1) / (2 * np.pi)) % 1.0) for x in X]


def figure(azim=0, elev=18, scale=1.62):
    """The camera looks at longitude −90° (the −y side), where the action is."""
    view = View(azim=azim, elev=elev, scale=scale, viewport=(-0.6, -0.15, 12.6, 7.8))
    return Figure(view, Sphere(R), PAPER)


class Flow:
    """N particles that glide along great circles from A[i] to B[i] as ``t``
    goes 0 → 1. ``retarget(Y, perm)`` starts a new leg from where they are."""

    def __init__(self, X):
        self.A = np.array(X, dtype=float)
        self.B = np.array(X, dtype=float)
        self.t = ValueTracker(1.0)

    def pos(self, i):
        return slerp(self.A[i], self.B[i], self.t.get_value(), radius=R)

    def retarget(self, targets):
        cur = np.array([self.pos(i) for i in range(len(self.A))])
        self.A, self.B = cur, np.array(targets, dtype=float)
        self.t.set_value(0.0)

    def geodesic(self, i, k=24):
        return [slerp(self.A[i], self.B[i], s, radius=R) for s in np.linspace(0, 1, k)]


def slots(fig, Y, width=1.4):
    """Hollow rings marking the target positions (hidden behind the sphere)."""
    from lemur.anim import Circle

    return [fig.view.pin(Circle(radius=0.05, stroke_color=fig.pal.ink, stroke_width=width, fill_opacity=0.0),
                         y, rule="hide") for y in Y]
