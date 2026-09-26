"""Coordinates on the torus: a meridian (u fixed) and a parallel (v fixed)
meet at p; the tangent plane there is spanned by T_u and T_v. Curves are drawn
as a paper figure draws them: the hidden parts thin and dashed."""
import numpy as np
from lemur.anim import Anim, Create, FadeIn, GrowFromCenter, ValueTracker
import torus_lib as TL

U0, V0 = 0.55, 0.9


class Frame(Anim):
    def build(self):
        fig = TL.figure(azim=-35, elev=30)
        self.add(*fig.backdrop(nu=72))
        pal = fig.pal
        vs = np.linspace(0, 2 * np.pi, 160)
        us = np.linspace(0, 2 * np.pi, 240)
        meridian = fig.curve(lambda: [TL.T(U0, v) for v in vs], color=pal.blue, closed=True)
        parallel = fig.curve(lambda: [TL.T(u, V0) for u in us], color=pal.green, closed=True)
        self.play(*[Create(m) for m in meridian], run_time=1.4)
        self.play(*[Create(m) for m in parallel], run_time=1.4)
        p = TL.T(U0, V0)
        dot = fig.dot(p)
        self.play(GrowFromCenter(dot), FadeIn(fig.label("p", p, offset=(-0.3, 0.3))), run_time=0.6)
        self.next()

        eu = TL.T_u(U0, V0); eu = eu / np.linalg.norm(eu)
        ev = TL.T_v(U0, V0); ev = ev / np.linalg.norm(ev)
        sheet = fig.sheet(lambda: [p + 1.1 * (a * eu + b * ev) for a, b in ((1, 1), (-1, 1), (-1, -1), (1, -1))],
                          anchor=lambda: p)
        au = fig.arrow(lambda: (p, 0.95 * eu), color=pal.green)
        av = fig.arrow(lambda: (p, 0.95 * ev), color=pal.blue)
        self.play(*[FadeIn(m) for m in sheet], run_time=0.8)
        self.add(au, av)
        self.play(FadeIn(au), FadeIn(av), FadeIn(fig.label(r"T_u", p + 1.05 * eu, offset=(0.25, 0.1), color=pal.green)),
                  FadeIn(fig.label(r"T_v", p + 1.05 * ev, offset=(0.05, 0.3), color=pal.blue)), run_time=0.8)
        self.next()
        self.play(*fig.view.reorient(azim=70, elev=40), run_time=4)
        self.next()
