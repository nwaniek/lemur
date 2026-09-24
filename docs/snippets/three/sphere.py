import numpy as np
from lemur.anim import Anim, View, Create, FadeIn, Circle

R = 2.0


class Sphere(Anim):
    def build(self):
        v = View(azim=-20, elev=20, scale=1.3)
        v.occluder = {"c": [0, 0, 0], "R": R, "cap": None}      # a solid sphere hides things

        t = np.linspace(0, 2 * np.pi, 121)[:-1]
        tilt = np.radians(35)

        def ring():                                            # a tilted great circle
            return [(R * np.cos(a), R * np.sin(a) * np.cos(tilt), R * np.sin(a) * np.sin(tilt)) for a in t]

        outline = Circle(radius=R * 1.3, color="#7a869a", stroke_width=2)   # an orthographic sphere's outline
        front = v.curve_fn(ring, closed=True, rule="vis", color="#c0392b", stroke_width=5)
        back = v.curve_fn(ring, closed=True, rule="hid", color="#c0392b", stroke_width=2.5,
                          dash=(0.12, 0.1))
        p = v.dot((0, -R * np.cos(tilt), -R * np.sin(tilt)), rule="hide", color="#2c69b0", radius=0.1)
        self.play(Create(outline), Create(front), Create(back), FadeIn(p), run_time=1.5)
        self.next()

        self.play(*v.reorient(azim=200, elev=10), run_time=5)  # the player re-splits every frame
        self.next()
