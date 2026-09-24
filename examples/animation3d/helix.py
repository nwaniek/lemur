"""The complex exponential e^{it}, in 3D.

Looked at straight down the z-axis it is just the unit circle in the complex
plane; tilt the view and it unwinds into a helix — an oscillation along z. The
3D is projected to the 2D animation plane at build time (see `lemur.anim.three`),
so orbiting the camera bakes into the ordinary morph tracks the runtime plays.
"""

import numpy as np

from lemur.anim import Anim, View, Create, FadeIn


class ComplexHelix(Anim):
    def build(self):
        sp = View(elev=90)                 # look down z: the complex plane, head-on

        loops, height = 3, 4.5
        tmax = loops * 2 * np.pi
        top = height / 2
        axis = dict(color="#9aa0a6", stroke_width=2)

        re_ax = sp.line([-1.7, 0, 0], [1.7, 0, 0], **axis)
        im_ax = sp.line([0, -1.7, 0], [0, 1.7, 0], **axis)
        z_ax = sp.line([0, 0, -top - 0.3], [0, 0, top + 0.3], **axis)
        re_l = sp.label("Re", [2.0, 0, 0], font_size=30, color="#5f6368")
        im_l = sp.label("Im", [0, 2.0, 0], font_size=30, color="#5f6368")
        t_l = sp.label("t", [0, 0, top + 0.55], font_size=30, color="#5f6368")

        helix = sp.parametric(
            lambda t: (np.cos(t), np.sin(t), (t / tmax - 0.5) * height),
            0, tmax, samples=200, color="#2b6cb0", stroke_width=5)

        # 1) the complex plane, head-on: e^{it} traces the unit circle
        self.add(re_ax, im_ax, re_l, im_l)
        self.play(Create(helix))
        self.next()

        # 2) tilt into 3D — the circle unwinds into an oscillation along z, and
        #    the t (z) axis fades in as the view turns
        self.play(FadeIn(z_ax), FadeIn(t_l), *sp.reorient(elev=26, azim=-30), run_time=3)
        self.next()
