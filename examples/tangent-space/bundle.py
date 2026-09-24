"""A tangent space everywhere: p travels across the dome and carries its plane
and a frame (e1, e2) along; the planes it leaves behind tilt with the surface."""
import numpy as np
from lemur.anim import Anim, View, Create, FadeIn, ValueTracker, MathTex
import dome as D

S0, S1 = 0.0, 1.0


def theta(s):
    return 0.3 + 0.75 * (2 * s - 1) ** 2        # up over the top and down again


def phi(s):
    return 2.0 - 2.8 * s                           # from the back round to the front


def at(s):
    return D.Point(theta(s), phi(s))


class Everywhere(Anim):
    def build(self):
        view = View(azim=-35, elev=28, scale=1.85, viewport=(-0.9, -0.1, 12.2, 7.8))
        view._data_origin = np.array([0.0, 0.0, 0.45 * D.R])
        s = ValueTracker(0.0)
        cur = lambda: at(s.get_value())                          # noqa: E731

        path = view.parametric(lambda u: D.S(theta(u), phi(u)), S0, S1, 120, color=D.YELLOW,
                               stroke_width=2.6)
        plane = D.moving_polygon(view, lambda: cur().square(1.05), fill_color=D.BLUE, fill_opacity=0.22,
                                 color=D.BLUE)
        e1 = D.arrow(view, lambda: (cur().p, 0.95 * cur().e1), color=D.RED, width=3.5)
        e2 = D.arrow(view, lambda: (cur().p, 0.95 * cur().e2), color=D.GREEN, width=3.5)
        pd = D.dot(view, lambda: cur().p)
        tl = D.label(view, r"T_pM", lambda: cur().p + 1.0 * cur().e1 + 1.0 * cur().e2,
                     offset=(0.2, 0.3), color=D.BLUE, scale=1.45)
        self.add(D.ground(view), D.dome(view))
        self.play(Create(path), FadeIn(plane), FadeIn(e1), FadeIn(e2), FadeIn(pd), FadeIn(tl), run_time=1.6)
        self.next()

        # beat 2 — travel, dropping a ghost plane now and then
        for stop in (0.33, 0.66, 1.0):
            ghost = view.polygon(cur().square(0.8), fill_color=D.BLUE, fill_opacity=0.1,
                                 color="#5a93a8", stroke_width=1.2)
            self.bring_to_back(ghost)
            self.play(FadeIn(ghost), run_time=0.3)
            self.play(s.animate(rate_func="smooth").set_value(stop), *view.reorient(azim=-35 + 20 * stop),
                      run_time=2.2)
        self.next()

        # beat 3 — all of them together
        tb = MathTex(r"TM = \bigsqcup_{p \in M} T_pM", color=D.INK).scale(1.44).move_to([4.7, 3.1])
        sub = MathTex(r"\text{the tangent bundle}", color="#8b98a5").scale(1.12).move_to([4.7, 2.3])
        self.play(FadeIn(tb), FadeIn(sub), run_time=1.0)
        self.next()
