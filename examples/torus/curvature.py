"""Gaussian curvature changes sign: positive on the outer half (the surface
bends the same way in both directions), negative in the hole (a saddle), zero
on the top and bottom circles. The solid is tinted by K."""
import numpy as np
from lemur.anim import Anim, Create, FadeIn
import torus_lib as TL


class Curvature(Anim):
    def build(self):
        fig = TL.figure(azim=-35, elev=38)
        shadow = fig.shadow()
        solid = fig.solid(nu=72, tint=TL.curvature_tint, tint_mix=0.55)
        outline = fig.silhouette()
        self.add(shadow, solid, outline)
        us = np.linspace(0, 2 * np.pi, 240)
        top = fig.curve(lambda: [TL.T(u, np.pi / 2) for u in us], color=fig.pal.ink, width=2.6, closed=True)
        bottom = fig.curve(lambda: [TL.T(u, -np.pi / 2) for u in us], color=fig.pal.ink, width=2.6, closed=True)
        self.play(*[Create(m) for m in top], *[Create(m) for m in bottom], run_time=1.6)
        self.next()
        self.play(*fig.view.reorient(azim=40, elev=70), run_time=3.5)
        self.next()
        self.play(*fig.view.reorient(azim=-35, elev=12), run_time=3.5)
        self.next()
