"""A tangent space everywhere: p travels over the dome carrying its plane and a
frame (e1, e2), leaving tilted ghost planes behind — the tangent bundle."""
import numpy as np
from lemur.anim import Anim, View, Create, FadeIn, ValueTracker, MathTex
import ill as I


def theta(s):
    return 0.3 + 0.75 * (2 * s - 1) ** 2


def phi(s):
    return 2.0 - 2.8 * s


def at(s):
    return I.Point(theta(s), phi(s))


class Everywhere(Anim):
    def build(self):
        view = View(azim=-35, elev=28, scale=1.85, viewport=(-0.9, -0.1, 12.2, 7.8))
        view._data_origin = np.array([0.0, 0.0, 0.45 * I.R])
        s = ValueTracker(0.0)
        cur = lambda: at(s.get_value())                          # noqa: E731
        self.add(I.shadow(view), I.dome(view), I.silhouette(view))

        path = I.curve(view, lambda: [I.S(theta(u), phi(u)) for u in np.linspace(0, 1, 120)],
                       color=I.ORANGE, width=3.2)
        sheet = I.tangent_plane(view, lambda: cur().square(1.05), grid=3, alpha=0.6, anchor=lambda: cur().p)
        e1 = I.arrow(view, lambda: (cur().p, 0.95 * cur().e1), color=I.RED, width=4.0)
        e2 = I.arrow(view, lambda: (cur().p, 0.95 * cur().e2), color=I.GREEN, width=4.0)
        pd = I.dot(view, lambda: cur().p)
        tl = I.label(view, r"T_pM", lambda: cur().p + 1.05 * cur().e1 + 1.05 * cur().e2,
                     offset=(0.25, 0.3), color="#c0661f", scale=1.45)
        self.play(*[Create(m) for m in path], run_time=1.2)
        self.play(FadeIn(sheet), FadeIn(e1), FadeIn(e2), FadeIn(pd), FadeIn(tl), run_time=1.0)
        self.next()

        # beat 2 — travel, dropping a ghost plane now and then
        for stop in (0.33, 0.66, 1.0):
            c = cur()
            ghost = I.tangent_plane(view, lambda c=c: c.square(0.8), grid=0, alpha=0.28, anchor=lambda c=c: c.p)
            self.play(FadeIn(ghost), run_time=0.3)
            self.bring_to_front(sheet, e1, e2, pd, tl)
            self.play(s.animate(rate_func="smooth").set_value(stop), *view.reorient(azim=-35 + 20 * stop),
                      run_time=2.2)
        self.next()

        # beat 3 — all of them together
        tb = MathTex(r"TM = \bigsqcup_{p \in M} T_pM", color=I.INK).scale(1.4).move_to([4.7, 3.1])
        sub = MathTex(r"\text{the tangent bundle}", color="#7a7f8c").scale(1.1).move_to([4.7, 2.2])
        self.play(FadeIn(tb), FadeIn(sub), run_time=1.0)
        self.next()
