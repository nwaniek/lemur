import numpy as np
from lemur.anim import (Anim, View, Create, FadeIn, ValueTracker, VShape, VGroup,
                        Circle, MathTex)
from lemur.anim import bezier as bz
import geom

A = np.array([0.0, 0.0, 1.0])
B = np.array([1.0, 0.0, 0.0])
C = np.array([0.0, 1.0, 0.0])


class Holonomy(Anim):
    def build(self):
        view = View(azim=-52, elev=22, scale=2.5, viewport=(-1.4, -0.2, 10.0, 7.2))
        sph = geom.sphere(view)
        path = np.vstack([geom.arc(A, B), geom.arc(B, C)[1:], geom.arc(C, A)[1:]])
        V0 = np.array([1.0, 0.0, 0.0])
        Vs = geom.transport_along(V0, path)
        loop = view.curve(path, color="#2b6cb0", stroke_width=3)

        prog = ValueTracker(0.0)

        def state():
            f = prog.get_value()
            i = f * (len(path) - 1)
            lo = min(int(i), len(path) - 2)
            a = i - lo
            return path[lo] * (1 - a) + path[lo + 1] * a, Vs[lo] * (1 - a) + Vs[lo + 1] * a

        dot = Circle(radius=0.05, fill_color="#c0392b", fill_opacity=1.0, stroke_width=0)
        dot.add_updater(lambda m: m.move_to(view.project(state()[0])))
        vec = geom.vector(view, state, color="#c0392b")
        ghost = geom.vector(view, lambda: (A, V0), color="#9aa0a6", width=3)

        self.add(sph)
        self.play(Create(loop), FadeIn(ghost))
        self.next()
        self.add(dot, vec)
        self.play(prog.animate(rate_func="linear").set_value(1.0), run_time=6)
        self.next()
        ang = MathTex(r"\Delta\theta = 90^\circ", color="#c0392b").scale(1.2).move_to([3.6, 2.4])
        self.play(FadeIn(ang))
        self.next()
