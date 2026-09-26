import numpy as np
from lemur.anim import Anim, View, Create, FadeIn
from lemur.anim.illustrate import Figure, Torus


class Knot(Anim):
    def build(self):
        fig = Figure(View(azim=-30, elev=30, scale=1.5, renderer="gpu"), Torus(2.0, 0.75))
        shadow, solid, outline = fig.backdrop(nu=48)
        knot = [fig.occ.surface(2 * s, 3 * s) for s in np.linspace(0, 2 * np.pi, 300)]
        curve = fig.curve(lambda: knot, color=fig.pal.red, closed=True)
        self.play(FadeIn(shadow), FadeIn(solid), Create(outline), run_time=1.2)
        self.next()
        self.play(*[Create(m) for m in curve], run_time=1.5)
        self.next()
        self.play(*fig.view.reorient(azim=110, elev=-12), run_time=4)   # the torus hides the knot
        self.next()
