"""Every direction you can walk: three curves through p, their velocities, the
plane they all lie in — T_pM — and a swing round until it is edge-on."""
import numpy as np
from lemur.anim import Anim, View, Create, FadeIn, FadeOut, ValueTracker, MathTex
import ill as I
from dome_math import edge_on_azim

P = I.Point(0.62, -0.75)
DIRS = [(0.35, I.BLUE), (1.55, I.GREEN), (2.65, I.PURPLE)]
AZ, EL = -35, 24


class Directions(Anim):
    def build(self):
        view = View(azim=AZ, elev=EL, scale=1.85, viewport=(-0.9, -0.1, 12.2, 7.8))
        view._data_origin = np.array([0.0, 0.0, 0.45 * I.R])
        self.add(I.shadow(view), I.dome(view), I.silhouette(view))

        # beat 1 — curves through p, in three directions
        curves = [I.curve(view, lambda w=P.dir(a): [P.exp(t * w) for t in np.linspace(-1.7, 1.7, 70)], color=c)
                  for a, c in DIRS]
        self.play(*[Create(m) for c in curves for m in c], run_time=2.0)
        pd, pl = I.dot(view, P.p), I.label(view, "p", P.p, offset=(-0.35, 0.42))
        self.add(pd, pl)
        self.next()

        # beat 2 — their velocities at p
        grow = ValueTracker(0.0)
        arrows = [I.arrow(view, lambda w=P.dir(a): (P.p, grow.get_value() * 1.25 * w), color=c) for a, c in DIRS]
        self.add(*arrows)
        self.play(grow.animate.set_value(1.0), run_time=1.0)
        self.next()

        # beat 3 — they all lie in one plane: the tangent space (slid in underneath)
        sheet = I.tangent_plane(view, lambda: P.square(1.65))
        corner = P.p + 1.45 * P.e1 - 1.45 * P.e2
        tl = I.label(view, r"T_pM", corner, offset=(0.0, -0.4), color="#c0661f", scale=1.8)
        self.play(FadeIn(sheet), FadeIn(tl), run_time=1.2)
        self.bring_to_front(*curves, *arrows, pd, pl)
        self.next()

        # beat 4 — swing round until the plane is edge-on: it only kisses the dome
        az = edge_on_azim(6, P.n, AZ)
        self.play(*view.reorient(azim=az, elev=6), run_time=3.0)
        note = MathTex(r"\text{touches only at } p", color=I.INK).scale(1.3).move_to([4.6, 3.0])
        self.play(FadeIn(note), run_time=0.6)
        self.next()

        # beat 5 — and back
        self.play(FadeOut(note), *view.reorient(azim=AZ, elev=EL), run_time=2.5)
        self.next()
