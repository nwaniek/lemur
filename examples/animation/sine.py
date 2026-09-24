"""A build-time animation for `!anim`: empty → coordinate system → sine on
−2π..2π → highlight −π..π. A 2D plot is just a top-down `View` view."""

import numpy as np

from lemur.anim import Anim, View, Create, FadeIn


class SineWave(Anim):
    def build(self):
        sp = View(elev=90, viewport=(0, 0, 12.6, 6.2)).fit((-2 * np.pi, 2 * np.pi), (-1.5, 1.5))

        axes = sp.axes(x=(-2 * np.pi, 2 * np.pi, np.pi), y=(-1.5, 1.5, 0.5), z=(0, 0),
                       stroke_width=1.6)
        self.play(Create(axes))                     # beat 1: the axes draw on
        self.next()

        curve = sp.plot(np.sin, -2 * np.pi, 2 * np.pi, color="#2b6cb0", stroke_width=5)
        self.play(Create(curve))                    # beat 2: the sine draws on
        self.next()

        band = sp.area(np.sin, -np.pi, np.pi, fill_color="#2b6cb0", fill_opacity=0.3)
        self.play(FadeIn(band))                     # beat 3: highlight −π..π
        self.next()
