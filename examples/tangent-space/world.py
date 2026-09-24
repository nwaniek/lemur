"""A curved world: the dome draws itself while the camera swings round, a point
p appears, and an ant walks a geodesic through p — its velocity always hugs the
surface."""
import numpy as np
from lemur.anim import Anim, View, Create, FadeIn, FadeOut, GrowFromCenter, LaggedStart, ValueTracker, MathTex
import dome as D

P = D.Point(0.62, -0.75)
W = P.dir(1.1)                           # the direction the ant walks through p


def gamma(t):
    return P.exp(t * W)


def gamma_dot(t):
    """d/dt exp_p(t w): unit speed, always tangent to the dome."""
    return -np.sin(t / D.R) * P.n + np.cos(t / D.R) * W


class CurvedWorld(Anim):
    def build(self):
        view = View(azim=-75, elev=24, scale=1.85, viewport=(-0.9, -0.1, 12.2, 7.8))
        view._data_origin = np.array([0.0, 0.0, 0.45 * D.R])      # centre the dome, not its base
        ground, wire = D.ground(view), D.dome(view)

        # beat 1 — the dome draws itself while the camera swings round
        self.add(ground)
        self.play(LaggedStart(*[Create(m) for m in wire], lag_ratio=0.07),
                  *view.reorient(azim=-35), run_time=3.5)
        self.next()

        # beat 2 — a point p
        pd = D.dot(view, P.p)
        pl = D.label(view, "p", P.p, offset=(-0.35, 0.4), color=D.YELLOW)
        self.play(GrowFromCenter(pd), FadeIn(pl), run_time=0.8)
        self.next()

        # beat 3 — an ant walks a geodesic through p ...
        path = view.parametric(gamma, -2.2, 1.7, 90, color=D.BLUE, stroke_width=4)
        tau = ValueTracker(-2.2)
        ant = D.dot(view, lambda: gamma(tau.get_value()), color=D.RED, radius=0.09)
        self.play(Create(path), run_time=1.4)
        self.add(ant)
        self.play(tau.animate(rate_func="smooth").set_value(0.0), run_time=2.4)
        # ... and at p its velocity appears
        vel = D.arrow(view, lambda: (gamma(tau.get_value()), 1.3 * gamma_dot(tau.get_value())), color=D.RED)
        link = D.label(view, r"\gamma'(0)", P.p + 1.3 * W, offset=(0.75, 0.3), color=D.RED, scale=1.45)
        self.play(FadeIn(vel), FadeIn(link), run_time=0.8)
        self.next()

        # beat 4 — keep walking: the velocity always lies flat against the dome
        ghost = D.arrow(view, lambda: (P.p, 1.3 * W), color="#8a4b4b", width=3)
        self.add(ghost)
        self.play(FadeOut(link), run_time=0.3)
        self.play(tau.animate(rate_func="smooth").set_value(1.7), run_time=2.6)
        note = MathTex(r"\gamma'(t)\ \text{is always}\\ \text{tangent}", color=D.INK).scale(1.28)
        note.move_to([5.1, 2.6])
        self.play(FadeIn(note), run_time=0.8)
        self.next()
