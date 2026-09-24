"""The optimal plan: every grain travels along a great circle to its slot;
trails show the map. Then a swing round, with the ring in place."""
import numpy as np
from lemur.anim import Anim, Create, FadeIn, FadeOut, MathTex, Circle
from lemur.anim.rate import smooth
import otlib as O

A, B = O.direction(28, -125), O.direction(5, -58)


def trails(fig, flow, cols, width=1.3, alpha=0.55):
    """A trail per particle along its geodesic, and Creates whose drawn tip
    rides exactly on the particle (the camera must hold still)."""
    lines, anims = [], []
    for i, c in enumerate(cols):
        pts = flow.geodesic(i)
        ln = fig.view.curve(pts, color=c, stroke_width=width)
        ln.set_stroke(opacity=alpha)
        r = fig.view.rate(pts)
        lines.append(ln)
        anims.append(Create(ln, rate_func=lambda a, r=r: r(smooth(a))))
    return lines, anims


class Transport(Anim):
    def build(self):
        fig = O.figure()
        X, Y = O.blob(A), O.ring(B)
        cols = O.colours_by_angle(X, A)
        perm = O.monge(X, Y)
        flow = O.Flow(X)

        ghosts = O.slots(fig, Y, width=1.4)
        dots = [fig.dot(lambda i=i: flow.pos(i), color=c, radius=0.055, rim=1.6) for i, c in enumerate(cols)]
        self.add(*fig.backdrop(), *ghosts, *dots)

        # beat 1 — follow the optimal map
        flow.retarget(Y[perm])
        lines, creates = trails(fig, flow, cols)
        self.play(flow.t.animate(rate_func="smooth").set_value(1.0), *creates, run_time=4.0)
        self.bring_to_front(*dots)
        self.next()

        # beat 2 — the cost of the plan
        w2 = MathTex(r"W_2^2(\mu,\nu) = \tfrac1N\sum_i d\big(x_i, T(x_i)\big)^2 = %.2f" % O.total_cost(X, Y, perm),
                     color=fig.pal.ink).scale(1.15).move_to([0.0, 3.35])
        self.play(FadeIn(w2), run_time=0.8)
        self.next()

        # beat 3 — the trails fade; swing round the finished ring
        self.play(*[FadeOut(ln) for ln in lines], FadeOut(w2), run_time=0.8)
        self.play(*fig.view.reorient(azim=50, elev=52), run_time=3.0)
        self.play(*fig.view.reorient(azim=0, elev=18), run_time=2.5)
        self.next()
