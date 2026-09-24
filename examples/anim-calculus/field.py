"""A vector field with a streamline traced through it."""
import numpy as np
from lemur.anim import Anim, Arrow, Circle, Create, VGroup


def vec(x, y):
    return np.array([-y - 0.18 * x, x - 0.18 * y])   # inward spiral


class VectorField(Anim):
    def build(self):
        field = VGroup()
        for gx in np.linspace(-3, 3, 9):
            for gy in np.linspace(-2, 2, 7):
                v = vec(gx, gy)
                n = np.hypot(*v) + 1e-9
                d = v / n * 0.42
                field.add(Arrow([gx, gy], [gx + d[0], gy + d[1]],
                                color="#9aa0a6", stroke_width=2, buff=0.0))
        self.play(Create(field), run_time=1.5)
        self.next()

        # a particle flowing along the field (RK-ish integration), traced on
        pts = [np.array([2.7, 0.4])]
        for _ in range(600):
            p = pts[-1]
            pts.append(p + 0.02 * vec(*p))
        stream = VGroup()
        arr = np.array(pts)
        from lemur.anim import VShape
        from lemur.anim import bezier as bz
        line = VShape(color="#c0392b", stroke_width=3)
        line.set_subpaths([bz.line_handles(arr)], [False])
        self.play(Create(line), run_time=4)             # trace the trajectory
        self.next()
