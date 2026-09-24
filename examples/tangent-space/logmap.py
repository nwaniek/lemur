"""Flattening the dome with log_p: the geodesic from p to q unrolls into a
straight arrow in the tangent plane, keeping its length. Then a whole geodesic
circle with its spokes unrolls — and has to stretch."""
import numpy as np
from lemur.anim import Anim, View, Create, FadeIn, FadeOut, ValueTracker, MathTex
import dome as D

P = D.Point(0.62, -0.75)
U = P.dir(1.75)                       # the direction towards q
DQ = 2.2                               # q's distance from p along the dome
TS = np.linspace(0.0, 1.0, 48)


class LogMap(Anim):
    def build(self):
        view = View(azim=-35, elev=30, scale=1.85, viewport=(-0.9, -0.1, 12.2, 7.8))
        view._data_origin = np.array([0.0, 0.0, 0.45 * D.R])
        plane = view.polygon(P.square(2.35), fill_color=D.BLUE, fill_opacity=0.12,
                             color=D.BLUE, stroke_width=1.2)
        self.add(D.ground(view), D.dome(view), plane, D.dot(view, P.p),
                 D.label(view, "p", P.p, offset=(-0.3, 0.3), color=D.YELLOW))

        # beat 1 — a point q and the shortest path to it
        lam = ValueTracker(0.0)
        vecs = [t * DQ * U for t in TS]
        geo = D.moving_curve(view, lambda: D.blended(P, vecs, lam), color=D.YELLOW, stroke_width=4.5)
        tip = lambda: D.blended(P, [DQ * U], lam)[0]            # noqa: E731
        qd = D.dot(view, tip, color=D.RED, radius=0.085)
        ql = D.label(view, "q", P.exp(DQ * U), offset=(0.35, -0.35), color=D.RED)
        self.play(FadeIn(qd), FadeIn(ql), run_time=0.6)
        self.play(Create(geo), run_time=1.6)
        self.next()

        # beat 2 — unroll it into the plane: that arrow is log_p(q)
        trace = view.parametric(lambda t: P.exp(t * DQ * U), 0, 1, 48, color="#7a6a3a", stroke_width=2.5)
        self.add(trace)
        self.bring_to_back(trace)
        self.play(FadeOut(ql), lam.animate(rate_func="smooth").set_value(1.0), run_time=2.6)
        ll = D.label(view, r"\log_p(q)", P.plane_point(DQ * U), offset=(0.2, 0.55), color=D.RED, scale=1.45)
        eq = MathTex(r"\|\log_p(q)\| = d(p,q)", color=D.INK).scale(1.36).move_to([4.7, 3.1])
        self.play(FadeIn(ll), FadeIn(eq), run_time=0.8)
        self.next()

        # beat 3 — a geodesic circle of radius r around p, and its spokes
        r = 1.5
        mu = ValueTracker(0.0)
        ring_v = [r * P.dir(a) for a in np.linspace(0, 2 * np.pi, 96)]
        ring = D.moving_curve(view, lambda: D.blended(P, ring_v, mu), closed=True,
                              color=D.GREEN, stroke_width=4)
        spokes = [D.moving_curve(view, lambda a=a: D.blended(P, [t * r * P.dir(a) for t in TS], mu),
                                 color=D.GREEN, stroke_width=2) for a in np.linspace(0, 2 * np.pi, 10, endpoint=False)]
        self.play(FadeOut(geo), FadeOut(qd), FadeOut(ll), FadeOut(trace), FadeOut(eq), run_time=0.6)
        self.play(*[Create(s) for s in spokes], Create(ring), run_time=1.8)
        dome_c = MathTex(r"C_{\text{dome}} = 2\pi R\sin\tfrac{r}{R}", color=D.GREEN).scale(1.36).move_to([4.6, 3.1])
        self.play(FadeIn(dome_c), run_time=0.6)
        self.next()

        # beat 4 — unroll the circle: the spokes keep their length, the rim must stretch
        self.play(mu.animate(rate_func="smooth").set_value(1.0), run_time=3.0)
        flat_c = MathTex(r"C_{\text{flat}} = 2\pi r \;>\; C_{\text{dome}}", color=D.YELLOW).scale(1.36)
        flat_c.move_to([4.6, 2.3])
        self.play(FadeIn(flat_c), run_time=0.8)
        self.next()
