"""exp_p shrink-wraps the tangent plane onto the dome: a polar grid in T_pM folds
down onto the surface; orbit to admire it; log_p unfolds it again."""
import numpy as np
from lemur.anim import Anim, View, Create, FadeIn, FadeOut, LaggedStart, ValueTracker, MathTex
import ill as I

P = I.Point(0.62, -0.75)
RMAX = 1.9
TS = np.linspace(0.0, 1.0, 36)


class ShrinkWrap(Anim):
    def build(self):
        view = View(azim=-35, elev=30, scale=1.85, viewport=(-0.9, -0.1, 12.2, 7.8))
        view._data_origin = np.array([0.0, 0.0, 0.45 * I.R])
        self.add(I.shadow(view), I.dome(view), I.silhouette(view))
        sheet = I.tangent_plane(view, lambda: P.square(2.1), grid=0, alpha=0.38)

        lam = ValueTracker(1.0)                                      # 1 = flat in T_pM, 0 = on the dome
        rings = [I.curve(view, lambda r=r: I.blended(P, [r * P.dir(a) for a in np.linspace(0, 2 * np.pi, 80)], lam),
                         color=I.ORANGE, width=3.0, closed=True) for r in np.linspace(RMAX / 4, RMAX, 4)]
        spokes = [I.curve(view, lambda a=a: I.blended(P, [t * RMAX * P.dir(a) for t in TS], lam),
                          color=I.BLUE, width=2.6) for a in np.linspace(0, 2 * np.pi, 16, endpoint=False)]
        pd = I.dot(view, P.p)

        # beat 1 — a polar grid in the tangent plane
        self.play(FadeIn(sheet), LaggedStart(*[Create(m) for s in spokes for m in s], lag_ratio=0.02),
                  LaggedStart(*[Create(m) for r in rings for m in r], lag_ratio=0.1), run_time=2.4)
        self.add(pd)
        tag = MathTex(r"T_pM", color="#c0661f").scale(1.5).move_to([4.8, 3.1])
        self.play(FadeIn(tag), run_time=0.5)
        self.next()

        # beat 2 — exp_p folds it onto the dome
        lab = MathTex(r"\exp_p : T_pM \to M", color=I.INK).scale(1.35).move_to([4.8, 3.1])
        self.play(FadeOut(sheet), FadeOut(tag), FadeIn(lab), lam.animate(rate_func="smooth").set_value(0.0),
                  run_time=3.4)
        self.next()

        # beat 3 — walk around it: a map of the dome centred at p (curves hide round the back)
        self.play(*view.reorient(azim=55, elev=40), run_time=4.0)
        self.next()

        # beat 4 — and log_p unfolds it again
        back = MathTex(r"\log_p = \exp_p^{-1}", color=I.RED).scale(1.35).move_to([4.8, 3.1])
        self.play(FadeOut(lab), FadeIn(back), *view.reorient(azim=-35, elev=30),
                  lam.animate(rate_func="smooth").set_value(1.0), run_time=3.4)
        self.next()
