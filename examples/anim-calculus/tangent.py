"""The derivative as a moving tangent line sliding along a curve."""
import numpy as np
from lemur.anim import Anim, View, Create, ValueTracker, VShape, Circle, MathTex
from lemur.anim import bezier as bz


def f(x):
    return 0.18 * x ** 3 - 0.6 * x + 1.2


def df(x):
    return 0.54 * x ** 2 - 0.6


class Tangent(Anim):
    def build(self):
        sp = View(elev=90, static=True, viewport=(0, -0.2, 12.0, 6.6)).fit((-3, 3), (-1, 4))
        self.add(sp.axes(x=(-3, 3, 1), y=(-1, 4, 1), z=(0, 0), numbers=True, font_size=20))
        curve = sp.plot(f, -3, 3, color="#2b6cb0", stroke_width=3.5)
        self.play(Create(curve))
        self.next()

        a = ValueTracker(-2.6)
        L = 1.6
        tan = VShape(color="#c0392b", stroke_width=3)
        tan.add_updater(lambda m: m.set_subpaths([bz.line_handles(np.array([
            sp.point(a.get_value() - L, f(a.get_value()) - df(a.get_value()) * L),
            sp.point(a.get_value() + L, f(a.get_value()) + df(a.get_value()) * L)]))], [False]))
        dot = Circle(radius=0.09, fill_color="#c0392b", fill_opacity=1.0, stroke_width=0)
        dot.add_updater(lambda m: m.move_to(sp.point(a.get_value(), f(a.get_value()))))
        note = MathTex(r"\text{slope} = f'(x)", color="#c0392b").scale(0.95).move_to(sp.point(-2.0, 3.5))

        self.add(tan, dot, note)
        self.play(a.animate.set_value(2.6), run_time=5)
        self.next()
