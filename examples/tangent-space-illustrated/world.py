"""A curved world: the shaded dome assembles itself row by row while the camera
swings round; a point p; an ant walks a geodesic through p and its velocity
rides along, always tangent."""
import numpy as np
from lemur.anim import (Anim, View, Create, FadeIn, FadeOut, GrowFromCenter, LaggedStart,
                        ValueTracker, MathTex)
import ill as I

P = I.Point(0.62, -0.75)
W = P.dir(1.1)


def gamma(t):
    return P.exp(t * W)


def gamma_dot(t):
    return -np.sin(t / I.R) * P.n + np.cos(t / I.R) * W


def stage(azim):
    view = View(azim=azim, elev=24, scale=1.85, viewport=(-0.9, -0.1, 12.2, 7.8))
    view._data_origin = np.array([0.0, 0.0, 0.45 * I.R])
    return view


class CurvedWorld(Anim):
    def build(self):
        view = stage(-75)
        shadow, dome, outline = I.shadow(view), I.dome(view), I.silhouette(view)

        # beat 1 — the dome assembles from the top down while the camera swings round
        under, top = dome.submobjects
        nv = 10                                              # faces come u-major, v (= down from the top) minor
        rows = sorted(range(len(top.submobjects)), key=lambda k: (k % nv, k // nv))
        self.play(FadeIn(shadow), LaggedStart(*[FadeIn(top.submobjects[k]) for k in rows], lag_ratio=0.004),
                  *view.reorient(azim=-35), run_time=3.5)
        self.play(FadeIn(under), Create(outline), run_time=0.8)
        self.next()

        # beat 2 — a point p
        pd = I.dot(view, P.p)
        self.play(GrowFromCenter(pd), FadeIn(I.label(view, "p", P.p, offset=(-0.35, 0.4))), run_time=0.8)
        self.next()

        # beat 3 — an ant walks a geodesic through p; its velocity grows out at p
        tau = ValueTracker(-2.2)
        path = I.curve(view, lambda: [gamma(t) for t in np.linspace(-2.2, 1.7, 90)], color=I.BLUE)
        ant = I.dot(view, lambda: gamma(tau.get_value()), color=I.RED, radius=0.1)
        self.play(*[Create(m) for m in path], run_time=1.4)
        self.add(ant)
        self.play(tau.animate(rate_func="smooth").set_value(0.0), run_time=2.4)
        grow = ValueTracker(0.0)
        vel = I.arrow(view, lambda: (gamma(tau.get_value()), grow.get_value() * 1.3 * gamma_dot(tau.get_value())))
        self.add(vel)
        tag = I.label(view, r"\gamma'(0)", P.p + 1.3 * W, offset=(0.75, 0.3), color=I.RED, scale=1.45)
        self.play(grow.animate.set_value(1.0), FadeIn(tag), run_time=0.9)
        self.next()

        # beat 4 — keep walking: the velocity always hugs the surface
        ghost = I.arrow(view, lambda: (P.p, 1.3 * W), color="#e6a39f", halo=False)
        self.add(ghost)
        self.bring_to_front(vel, ant)                   # the ghost stays underneath the live arrow
        self.play(FadeOut(tag), run_time=0.3)
        self.play(tau.animate(rate_func="smooth").set_value(1.7), run_time=2.6)
        note = MathTex(r"\gamma'(t)\ \text{is always}\\ \text{tangent}", color=I.INK).scale(1.3).move_to([5.1, 2.6])
        self.play(FadeIn(note), run_time=0.8)
        self.next()
