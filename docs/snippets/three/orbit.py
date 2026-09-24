import numpy as np
from lemur.anim import Anim, View, Create


class Ripple(Anim):
    def build(self):
        v = View(azim=-30, elev=25, scale=1.1)
        axes = v.axes(x=3, y=3, z=1.5, stroke_width=1.5)
        ripple = v.surface(lambda x, y: (x, y, np.cos(2 * np.hypot(x, y)) * np.exp(-0.25 * (x * x + y * y))),
                           (-3, 3), (-3, 3), u_lines=16, v_lines=16, samples=40,
                           color="#2c69b0", stroke_width=1.4)
        self.play(Create(axes), Create(ripple), run_time=2)
        self.next()

        self.play(*v.reorient(azim=60, elev=55), run_time=4)    # orbit the camera
        self.next()
