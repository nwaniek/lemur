"""Orthographic vs perspective — the same row of equal cubes on a floor grid,
side by side. Under perspective the far cubes shrink and the grid lines converge;
orthographic keeps them all the same size (parallel projection)."""
import numpy as np
from lemur.anim import Anim, View, Create, FadeIn, VGroup, panel

BLUE, GREY = "#2b6cb0", "#c9ced3"
CUBE = dict(fill_opacity=0.0, stroke_width=1.7, color=BLUE)   # wireframe


def scene(v):
    g = VGroup()
    for gx in np.linspace(-3, 3, 7):
        g.add(v.line((gx, -3.2, -1.0), (gx, 3.2, -1.0), color=GREY, stroke_width=1.0))
    for gy in np.linspace(-3.2, 3.2, 9):
        g.add(v.line((-3, gy, -1.0), (3, gy, -1.0), color=GREY, stroke_width=1.0))
    return g


def cubes(v):
    return VGroup(*[v.box((0.0, (k - 1.5) * 1.9, -0.35), 1.0, **CUBE) for k in range(4)])


class Projection(Anim):
    def build(self):
        W, H = 6.2, 6.6
        left = View(azim=32, elev=20, scale=0.82, viewport=(-3.4, -0.3, W, H))
        right = View(azim=32, elev=20, scale=0.82, viewport=(3.4, -0.3, W, H), perspective=7.5)

        frames = VGroup(panel(-3.4, -0.3, W, H, "orthographic"),
                        panel(3.4, -0.3, W, H, "perspective"))
        grids = VGroup(scene(left), scene(right))
        blocks = VGroup(cubes(left), cubes(right))

        self.play(FadeIn(frames), FadeIn(grids))       # the two framed floors
        self.next()
        self.play(Create(blocks))                       # identical cubes in each
        self.next()
