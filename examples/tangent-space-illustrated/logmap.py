"""Flattening the dome with log_p: the geodesic to q unrolls into a straight
arrow in the tangent plane; then a geodesic circle and its spokes unroll — the
spokes keep their length, the rim has to stretch."""
import numpy as np
from lemur.anim import Anim, View, Create, FadeIn, FadeOut, ValueTracker, MathTex
import ill as I

P = I.Point(0.62, -0.75)
U = P.dir(1.75)
DQ = 2.2
TS = np.linspace(0.0, 1.0, 48)


class LogMap(Anim):
    def build(self):
        view = View(azim=-35, elev=30, scale=1.85, viewport=(-0.9, -0.1, 12.2, 7.8))
        view._data_origin = np.array([0.0, 0.0, 0.45 * I.R])
        self.add(I.shadow(view), I.dome(view), I.silhouette(view),
                 I.tangent_plane(view, lambda: P.square(2.35), alpha=0.32),
                 I.dot(view, P.p), I.label(view, "p", P.p, offset=(-0.35, 0.42)))

        # beat 1 — a point q and the shortest path to it
        lam = ValueTracker(0.0)
        vecs = [t * DQ * U for t in TS]
        geo = I.curve(view, lambda: I.blended(P, vecs, lam), color=I.ORANGE, width=4.5)
        qd = I.dot(view, lambda: I.blended(P, [DQ * U], lam)[0], color=I.RED, radius=0.1)
        ql = I.label(view, "q", P.exp(DQ * U), offset=(0.35, -0.4), color=I.RED)
        self.play(*[Create(m) for m in geo], run_time=1.6)
        self.add(qd)
        self.play(FadeIn(ql), run_time=0.5)
        self.next()

        # beat 2 — unroll it into the plane: that arrow is log_p(q)
        trace = I.curve(view, lambda: [P.exp(t * DQ * U) for t in TS], color="#f3c49b", width=3, halo=False)
        self.add(trace)
        self.bring_to_front(geo, qd)
        self.play(FadeOut(ql), lam.animate(rate_func="smooth").set_value(1.0), run_time=2.6)
        ll = I.label(view, r"\log_p(q)", P.plane_point(DQ * U), offset=(0.2, 0.55), color=I.RED, scale=1.45)
        eq = MathTex(r"\|\log_p(q)\| = d(p,q)", color=I.INK).scale(1.35).move_to([4.7, 3.1])
        self.play(FadeIn(ll), FadeIn(eq), run_time=0.8)
        self.next()

        # beat 3 — a geodesic circle of radius r around p, and its spokes
        r = 1.5
        mu = ValueTracker(0.0)
        ring_v = [r * P.dir(a) for a in np.linspace(0, 2 * np.pi, 96)]
        ring = I.curve(view, lambda: I.blended(P, ring_v, mu), color=I.GREEN, width=4.5, closed=True)
        spokes = [I.curve(view, lambda a=a: I.blended(P, [t * r * P.dir(a) for t in TS], mu),
                          color=I.GREEN, width=2.2) for a in np.linspace(0, 2 * np.pi, 10, endpoint=False)]
        self.play(*[FadeOut(m) for m in (geo, qd, ll, trace, eq)], run_time=0.6)
        self.play(*[Create(m) for s in spokes for m in s], *[Create(m) for m in ring], run_time=1.8)
        dome_c = MathTex(r"C_{\text{dome}} = 2\pi R\sin\tfrac{r}{R}", color=I.GREEN).scale(1.35).move_to([4.6, 3.1])
        self.play(FadeIn(dome_c), run_time=0.6)
        self.next()

        # beat 4 — unroll the circle: spokes keep their length, the rim must stretch
        self.play(mu.animate(rate_func="smooth").set_value(1.0), run_time=3.0)
        flat_c = MathTex(r"C_{\text{flat}} = 2\pi r \;>\; C_{\text{dome}}", color="#c0661f").scale(1.35)
        flat_c.move_to([4.6, 2.3])
        self.play(FadeIn(flat_c), run_time=0.8)
        self.next()
