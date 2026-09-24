"""A 3-D bar chart in perspective, with solid z-sorted faces so nearer bars
correctly hide farther ones. Bars fade in row by row."""
import numpy as np
from lemur.anim import Anim, View, FadeIn, VGroup

TOP, SIDE = "#a9cbee", "#5a8fc7"


def bar(v, gx, gy, h, w=0.7):
    # a box on z=0 of height h; the top face is lighter for a lit look
    b = v.box((gx, gy, h / 2), (w, w, h), fill_color=SIDE, fill_opacity=0.97,
              color="#1f4e79", stroke_width=0.5)
    b[1].set_fill(TOP)                        # faces are [bottom, top, …] → [1] is the top
    return b


class Bars3D(Anim):
    def build(self):
        v = View(azim=35, elev=24, scale=0.62, perspective=13,
                    viewport=(0.4, -0.2, 12.5, 7.2))
        xs = np.arange(-2, 3)
        ys = np.arange(-2, 3)
        rng = np.random.default_rng(1)
        heights = {(gx, gy): 0.6 + 2.4 * np.exp(-((gx) ** 2 + (gy) ** 2) / 6) + 0.3 * rng.random()
                   for gx in xs for gy in ys}

        # reveal far rows first so occlusion reads correctly as they appear
        for gy in sorted(ys, reverse=True):
            row = VGroup(*[bar(v, gx, gy, heights[(gx, gy)]) for gx in xs])
            self.play(FadeIn(row), run_time=0.6)
            self.next()
