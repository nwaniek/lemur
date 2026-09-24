import numpy as np
from lemur.anim import Anim, View, Create, FadeIn, ValueTracker


def integrate(n=2800, dt=0.008, s=10.0, r=28.0, b=8.0 / 3.0):
    p = np.empty((n, 3)); p[0] = (0.1, 0.0, 1.05)
    for i in range(1, n):
        x, y, z = p[i - 1]
        p[i] = p[i - 1] + dt * np.array([s * (y - x), x * (r - z) - y, x * y - b * z])
    return p


class Lorenz(Anim):
    def build(self):
        p = integrate()
        p = p - p.mean(0)
        p = p / np.abs(p).max() * 2.5
        sp = View(azim=-8, elev=14, scale=1.5)          # classic x–z butterfly, tilted

        axes = sp.axes(x=2.9, y=2.9, z=2.9)
        xl = sp.label("x", [3.2, 0, 0], font_size=26, color="#5f6368")
        yl = sp.label("y", [0, 3.2, 0], font_size=26, color="#5f6368")
        zl = sp.label("z", [0, 0, 3.2], font_size=26, color="#5f6368")
        curve = sp.curve(p, color="#2b6cb0", stroke_width=1.5)

        # a marker that rides the growing head of the trajectory as it draws on
        prog = ValueTracker(0.0)
        head = sp.trace_dot(p, prog, color="#c0392b", radius=0.1)

        self.play(FadeIn(axes), FadeIn(xl), FadeIn(yl), FadeIn(zl))
        self.next()
        self.add(head)
        self.play(Create(curve, rate_func="linear"),
                  prog.animate(rate_func="linear").set_value(1.0), run_time=6)
        self.next()
