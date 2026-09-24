"""Not every plan is optimal: a random matching tangles; the optimal one never
crosses itself (cyclical monotonicity)."""
import numpy as np
from lemur.anim import Anim, FadeIn, FadeOut, MathTex, Circle
import otlib as O
from transport import trails

A, B = O.direction(28, -125), O.direction(5, -58)


class Compare(Anim):
    def build(self):
        fig = O.figure()
        X, Y = O.blob(A), O.ring(B)
        cols = O.colours_by_angle(X, A)
        rnd = np.random.default_rng(7).permutation(O.N)
        opt = O.monge(X, Y)
        flow = O.Flow(X)
        dots = [fig.dot(lambda i=i: flow.pos(i), color=c, radius=0.055, rim=1.6) for i, c in enumerate(cols)]
        self.add(*fig.backdrop(), *dots)

        def leg(perm, label, where):
            flow.retarget(Y[perm])
            lines, creates = trails(fig, flow, cols, width=1.1, alpha=0.5)
            self.play(flow.t.animate(rate_func="smooth").set_value(1.0), *creates, run_time=3.5)
            self.bring_to_front(*dots)
            txt = MathTex(label % O.total_cost(X, Y, perm), color=fig.pal.ink).scale(1.1).move_to(where)
            self.play(FadeIn(txt), run_time=0.6)
            return lines, txt

        # beat 1 — a random matching: a tangle
        lines, t1 = leg(rnd, r"\text{random: } \tfrac1N\textstyle\sum d^2 = %.2f", [-3.6, 3.35])
        self.next()

        # beat 2 — back to the start …
        flow.retarget(X)
        self.play(*[FadeOut(ln) for ln in lines], flow.t.animate(rate_func="smooth").set_value(1.0), run_time=2.0)
        self.next()

        # beat 3 — … and the optimal plan: no two paths cross
        lines, t2 = leg(opt, r"\text{optimal: } \tfrac1N\textstyle\sum d^2 = %.2f", [3.6, 3.35])
        self.next()
