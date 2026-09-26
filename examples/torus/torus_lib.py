"""Shared geometry for the torus deck: the torus of radii R (around the axis)
and r (around the tube), its Gaussian curvature, and geodesics — integrated
from the geodesic equations of the metric ds² = (R + r cos v)² du² + r² dv².

The figures are drawn with lemur.anim.illustrate in a GPU view, so the torus
hides what is behind it from any angle, and print gets exact vector stills."""
import numpy as np
from lemur.anim import View
from lemur.anim.illustrate import Figure, Torus, PAPER
from lemur.anim.color import interpolate_color

R, r = 2.0, 0.78
WARM, COOL, ZERO = "#e0703a", "#3f7cc0", "#f4f1ea"


def T(u, v):
    return np.array([(R + r * np.cos(v)) * np.cos(u), (R + r * np.cos(v)) * np.sin(u), r * np.sin(v)])


def T_u(u, v):
    return np.array([-(R + r * np.cos(v)) * np.sin(u), (R + r * np.cos(v)) * np.cos(u), 0.0])


def T_v(u, v):
    return np.array([-r * np.sin(v) * np.cos(u), -r * np.sin(v) * np.sin(u), r * np.cos(v)])


def gauss(v):
    """Gaussian curvature: positive on the outside, negative in the hole."""
    return np.cos(v) / (r * (R + r * np.cos(v)))


def curvature_tint(u, v):
    k = gauss(v) * r * (R - r)                           # scaled to about [-1, 1]
    return interpolate_color(ZERO, WARM if k > 0 else COOL, min(1.0, abs(k) ** 0.7)).hexa()[:7]


def geodesic(u0, v0, angle, length, n=400):
    """A unit-speed geodesic from (u0, v0), leaving at ``angle`` to the parallel
    through it (0 = along u), as 3-D points (RK4 on u'' and v'')."""
    def rhs(s):
        u, v, du, dv = s
        w = R + r * np.cos(v)
        return np.array([du, dv, 2 * r * np.sin(v) / w * du * dv, -w * np.sin(v) / r * du * du])

    w0 = R + r * np.cos(v0)
    s = np.array([u0, v0, np.cos(angle) / w0, np.sin(angle) / r])
    h = length / n
    out = [T(s[0], s[1])]
    for _ in range(n):
        k1 = rhs(s); k2 = rhs(s + h / 2 * k1); k3 = rhs(s + h / 2 * k2); k4 = rhs(s + h * k3)
        s = s + h / 6 * (k1 + 2 * k2 + 2 * k3 + k4)
        out.append(T(s[0], s[1]))
    return np.array(out)


def figure(azim=-35, elev=30, scale=1.6):
    view = View(azim=azim, elev=elev, scale=scale, renderer="gpu")
    return Figure(view, Torus(R, r), PAPER)
