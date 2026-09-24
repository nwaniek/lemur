"""Every direction you can walk: three curves through p, their velocities, and
the plane they all lie in — T_pM. Then the camera swings round until the plane
is edge-on: it touches the dome at p and nowhere else."""
import numpy as np
from lemur.anim import Anim, View, Create, FadeIn, FadeOut, ValueTracker, MathTex
import dome as D

P = D.Point(0.62, -0.75)
DIRS = [(0.35, D.BLUE), (1.55, D.GREEN), (2.65, D.PURPLE)]
AZ, EL = -35, 24


class Directions(Anim):
    def build(self):
        view = View(azim=AZ, elev=EL, scale=1.85, viewport=(-0.9, -0.1, 12.2, 7.8))
        view._data_origin = np.array([0.0, 0.0, 0.45 * D.R])
        self.add(D.ground(view), D.dome(view), D.dot(view, P.p),
                 D.label(view, "p", P.p, offset=(-0.28, 0.3), color=D.YELLOW))

        # beat 1 — curves through p, in three directions
        curves = [view.parametric(lambda t, w=P.dir(a): P.exp(t * w), -1.7, 1.7, 70,
                                  color=c, stroke_width=3.5) for a, c in DIRS]
        self.play(*[Create(c) for c in curves], run_time=2.0)
        self.next()

        # beat 2 — their velocities at p
        arrows = [D.arrow(view, lambda w=P.dir(a): (P.p, 1.25 * w), color=c) for a, c in DIRS]
        self.play(*[FadeIn(a) for a in arrows], run_time=1.0)
        self.next()

        # beat 3 — they all lie in one plane: the tangent space
        plane = view.polygon(P.square(1.65), fill_color=D.BLUE, fill_opacity=0.18,
                             color=D.BLUE, stroke_width=1.5)
        self.bring_to_back(plane)
        corner = P.p + 1.45 * P.e1 - 1.45 * P.e2
        tl = D.label(view, r"T_pM", corner, offset=(0.0, -0.35), color=D.BLUE, scale=1.8)
        self.play(FadeIn(plane), FadeIn(tl), run_time=1.2)
        self.next()

        # beat 4 — swing round until the plane is edge-on: it only *kisses* the dome
        az = D.edge_on_azim(6, P.n, AZ)
        self.play(*view.reorient(azim=az, elev=6), run_time=3.0)
        note = MathTex(r"\text{touches only at } p", color=D.INK).scale(1.28).move_to([4.6, 3.0])
        self.play(FadeIn(note), run_time=0.6)
        self.next()

        # beat 5 — and back
        self.play(FadeOut(note), *view.reorient(azim=AZ, elev=EL), run_time=2.5)
        self.next()
