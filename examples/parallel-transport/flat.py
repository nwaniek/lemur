"""In the flat plane, parallel transport is trivial: a vector carried around a
loop always stays parallel to itself, and returns exactly unchanged."""
import numpy as np
from lemur.anim import Anim, View, Create, FadeIn, ValueTracker, Circle
import geom

SQ = np.array([(-2, -2, 0), (2, -2, 0), (2, 2, 0), (-2, 2, 0), (-2, -2, 0)], dtype=float)


class Flat(Anim):
    def build(self):
        view = View(elev=90, viewport=(0, 0, 10.5, 6.4)).fit((-3.4, 3.4), (-3.1, 3.1))
        loop = view.curve(SQ, color="#9aa0a6", stroke_width=2)
        path = np.vstack([np.linspace(SQ[i], SQ[i + 1], 40) for i in range(4)])
        V = np.array([0.0, 1.4, 0.0])                 # constant → parallel in flat space

        prog = ValueTracker(0.0)

        def state():
            f = prog.get_value()
            i = f * (len(path) - 1)
            lo = min(int(i), len(path) - 2)
            a = i - lo
            return path[lo] * (1 - a) + path[lo + 1] * a, V

        dot = Circle(radius=0.07, fill_color="#c0392b", fill_opacity=1.0, stroke_width=0)
        dot.add_updater(lambda m: m.move_to(view.project(state()[0])))
        vec = geom.vector(view, state, color="#c0392b", scale=1.0, head=0.22, hw=0.12)
        ghost = geom.vector(view, lambda: (SQ[0], V), color="#c9ced3", width=3, scale=1.0, head=0.22, hw=0.12)

        self.add(loop, ghost)
        self.play(Create(loop))
        self.next()
        self.add(dot, vec)
        self.play(prog.animate(rate_func="linear").set_value(1.0), run_time=5)
        self.next()
