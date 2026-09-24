"""exp_p shrink-wraps the tangent plane onto the dome: a polar grid drawn in
T_pM folds down onto the surface — straight lines through p become geodesics,
circles become geodesic circles. Orbit to admire it, then unwrap with log_p."""
import numpy as np
from lemur.anim import Anim, View, Create, FadeIn, FadeOut, LaggedStart, ValueTracker, MathTex
import dome as D

P = D.Point(0.62, -0.75)
RMAX = 1.9
TS = np.linspace(0.0, 1.0, 40)


class ShrinkWrap(Anim):
    def build(self):
        view = View(azim=-35, elev=30, scale=1.85, viewport=(-0.9, -0.1, 12.2, 7.8))
        view._data_origin = np.array([0.0, 0.0, 0.45 * D.R])
        self.add(D.ground(view), D.dome(view, stroke_width=1.0), D.dot(view, P.p),
                 D.label(view, "p", P.p, offset=(-0.3, 0.32), color=D.YELLOW))

        lam = ValueTracker(1.0)                                  # 1 = flat in T_pM, 0 = on the dome
        rings = [D.moving_curve(view, lambda r=r: D.blended(P, [r * P.dir(a) for a in np.linspace(0, 2 * np.pi, 90)], lam),
                                closed=True, color=D.YELLOW, stroke_width=2.4)
                 for r in np.linspace(RMAX / 4, RMAX, 4)]
        spokes = [D.moving_curve(view, lambda a=a: D.blended(P, [t * RMAX * P.dir(a) for t in TS], lam),
                                 color=D.BLUE, stroke_width=2.4)
                  for a in np.linspace(0, 2 * np.pi, 16, endpoint=False)]
        plane = view.polygon(P.square(2.1), fill_color=D.BLUE, fill_opacity=0.14, color=D.BLUE, stroke_width=1.2)

        # beat 1 — a polar grid in the tangent plane
        self.play(FadeIn(plane), LaggedStart(*[Create(s) for s in spokes], lag_ratio=0.05),
                  LaggedStart(*[Create(r) for r in rings], lag_ratio=0.2), run_time=2.4)
        tag = MathTex(r"T_pM", color=D.BLUE).scale(1.5).move_to([4.8, 3.1])
        self.play(FadeIn(tag), run_time=0.5)
        self.next()

        # beat 2 — exp_p folds it onto the dome
        lab = MathTex(r"\exp_p : T_pM \to M", color=D.YELLOW).scale(1.44).move_to([4.8, 3.1])
        self.play(FadeOut(plane), FadeOut(tag), FadeIn(lab), lam.animate(rate_func="smooth").set_value(0.0),
                  run_time=3.4)
        self.next()

        # beat 3 — walk around it: a map of the dome, centred at p
        self.play(*view.reorient(azim=55, elev=40), run_time=4.0)
        self.next()

        # beat 4 — and log_p unfolds it again
        back = MathTex(r"\log_p = \exp_p^{-1}", color=D.RED).scale(1.44).move_to([4.8, 3.1])
        self.play(FadeOut(lab), FadeIn(back), *view.reorient(azim=-35, elev=30),
                  lam.animate(rate_func="smooth").set_value(1.0), run_time=3.4)
        self.next()
