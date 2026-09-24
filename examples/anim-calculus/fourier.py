"""A square wave emerging from its odd harmonics (Fourier series)."""
import numpy as np
from lemur.anim import Anim, View, Create, Transform, FadeIn, MathTex


def partial(k):
    def g(x):
        return (4 / np.pi) * sum(np.sin((2 * i + 1) * x) / (2 * i + 1) for i in range(k))
    return g


class Fourier(Anim):
    def build(self):
        sp = View(elev=90, static=True, viewport=(0, -0.2, 12.6, 6.0)).fit((-np.pi, np.pi), (-1.5, 1.5))
        self.add(sp.axes(x=(-3, 3, 1), y=(-1.5, 1.5, 0.5), z=(0, 0), numbers=True, font_size=18))
        curve = sp.plot(partial(1), -np.pi, np.pi, color="#2b6cb0", stroke_width=3.5)
        label = MathTex(r"\tfrac{4}{\pi}\sum_{k\,\mathrm{odd}} \tfrac{\sin kx}{k}",
                        color="#5f6368").move_to(sp.point(1.9, 1.25))
        self.add(label)
        self.play(Create(curve))
        self.next()
        for k in (2, 3, 5, 10):
            self.play(Transform(curve, sp.plot(partial(k), -np.pi, np.pi, color="#2b6cb0", stroke_width=3.5)))
            self.next()
