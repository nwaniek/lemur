"""Geodesics from one point: straight lines of the surface. Some wind around
the outside, some dive through the hole — each is drawn out as the camera
turns, its hidden stretches dashed."""
import numpy as np
from lemur.anim import Anim, Create, GrowFromCenter
from lemur.anim.rate import smooth
import torus_lib as TL

U0, V0 = -0.3, 0.2
ANGLES = [0.35, 0.95, 1.45, 2.3]


class Geodesics(Anim):
    def build(self):
        fig = TL.figure(azim=-25, elev=34)
        self.add(*fig.backdrop(nu=72))
        pal = fig.pal
        p = TL.T(U0, V0)
        dot = fig.dot(p, color=pal.red)
        self.play(GrowFromCenter(dot), run_time=0.5)
        self.next()
        cols = [pal.blue, pal.green, pal.purple, pal.orange]
        for k, (a, c) in enumerate(zip(ANGLES, cols)):
            pts = TL.geodesic(U0, V0, a, 14.0)
            g = fig.curve(lambda pts=pts: pts, color=c, width=3.4)
            self.play(*[Create(m, rate_func="linear") for m in g], *fig.view.reorient(azim=-25 + 25 * (k + 1)),
                      run_time=2.2)
            self.bring_to_front(dot)
            if k in (1, 3):
                self.next()
