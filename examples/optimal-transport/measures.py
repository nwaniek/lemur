"""Two ways to spread the same amount of sand: a blob μ (source) and a ring ν
(target) on a sphere. The camera orbits to show the world is curved."""
import numpy as np
from lemur.anim import Anim, Create, FadeIn, GrowFromCenter, LaggedStart, MathTex, Circle
import otlib as O

A, B = O.direction(28, -125), O.direction(5, -58)


class Measures(Anim):
    def build(self):
        fig = O.figure()
        shadow, solid, outline = fig.backdrop()
        X, Y = O.blob(A), O.ring(B)
        cols = O.colours_by_angle(X, A)

        self.play(FadeIn(shadow), FadeIn(solid), run_time=1.2)
        self.play(*[Create(m) for m in outline], run_time=0.8)
        self.next()

        # the source: N grains of sand, one colour per direction around its centre
        dots = [fig.dot(x, color=c, radius=0.055, rim=1.6) for x, c in zip(X, cols)]
        self.play(LaggedStart(*[GrowFromCenter(d) for d in dots], lag_ratio=0.01), run_time=2.0)
        mu = fig.label(r"\mu", O.R * 1.12 * A, offset=(-0.5, 0.3), scale=1.8)
        self.play(FadeIn(mu), run_time=0.5)
        self.next()

        # the target: where the sand should end up (empty slots)
        ghosts = O.slots(fig, Y)
        self.play(LaggedStart(*[FadeIn(g) for g in ghosts], lag_ratio=0.01), run_time=1.6)
        nu = fig.label(r"\nu", O.R * 1.12 * B, offset=(0.6, 0.35), scale=1.8)
        self.play(FadeIn(nu), run_time=0.5)
        self.next()

        # swing round: this is a curved world — straight lines are great circles
        self.play(*fig.view.reorient(azim=55, elev=45), run_time=3.0)
        self.play(*fig.view.reorient(azim=0, elev=18), run_time=2.5)
        self.next()
