"""A torus assembles; the camera goes round it and under it — the outline and
the shading follow, and it hides itself correctly from every side."""
import numpy as np
from lemur.anim import Anim, Create, FadeIn
import torus_lib as TL


class Shape(Anim):
    def build(self):
        fig = TL.figure(azim=-35, elev=30)
        shadow, solid, outline = fig.backdrop(nu=72)
        self.play(FadeIn(shadow), FadeIn(solid), run_time=1.2)
        self.play(Create(outline), run_time=0.8)
        self.next()
        self.play(*fig.view.reorient(azim=55, elev=62), run_time=3.5)
        self.next()
        self.play(*fig.view.reorient(azim=150, elev=8), run_time=3.5)
        self.next()
        self.play(*fig.view.reorient(azim=-35, elev=30), run_time=2.5)
        self.next()
