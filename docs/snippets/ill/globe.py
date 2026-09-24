import numpy as np
from lemur.anim import Anim, View, Create, FadeIn, GrowFromCenter
from lemur.anim.illustrate import Figure, Sphere, slerp, unit

R = 2.0
A = R * unit([-0.46, -0.62, 0.63])        # two points on the side facing the camera
B = R * unit([0.77, 0.09, 0.63])


def geodesic(s):
    return slerp(A, B, s, radius=R)


class Globe(Anim):
    def build(self):
        fig = Figure(View(azim=-30, elev=22, scale=1.55), Sphere(R))
        shadow, solid, outline = fig.backdrop(nu=24)
        self.play(FadeIn(shadow), FadeIn(solid), Create(outline), run_time=1.5)
        self.next()

        arc = fig.curve(lambda: [geodesic(s) for s in np.linspace(0, 1, 60)], color=fig.pal.blue)
        pa, pb = fig.dot(A), fig.dot(B, color=fig.pal.red)
        velocity = fig.arrow(lambda: (A, 1.1 * unit(geodesic(0.01) - A)))     # tangent at A
        self.play(*[Create(m) for m in arc], GrowFromCenter(pa), GrowFromCenter(pb), run_time=1.5)
        self.add(velocity)
        self.play(FadeIn(velocity), FadeIn(fig.label(r"\gamma", geodesic(0.5), offset=(0.0, 0.4))))
        self.next()

        self.play(*fig.view.reorient(azim=150, elev=5), run_time=5)    # it turns into a hidden line
        self.next()
