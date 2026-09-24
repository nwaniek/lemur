import numpy as np
from lemur.anim import Anim, View, Create, ValueTracker, Dot


class Tangent(Anim):
    def build(self):
        v = View(elev=90, viewport=(0, 0, 12.6, 6.4)).fit((-3, 3), (-1.5, 4.5))
        f = lambda x: 0.4 * x ** 2
        self.play(Create(v.axes(x=(-3, 3, 1), y=(-1, 4, 1), z=(0, 0))),
                  Create(v.plot(f, -3, 3, color="#2c69b0", stroke_width=5)))
        self.next()

        x = ValueTracker(-2.5)                       # the point of contact, animatable

        def tangent_points():
            x0 = x.get_value()
            k = 0.8 * x0                              # f'(x0)
            return [(x0 - 1.2, f(x0) - 1.2 * k, 0), (x0 + 1.2, f(x0) + 1.2 * k, 0)]

        line = v.curve_fn(tangent_points, color="#c0392b", stroke_width=5)
        dot = v.dot(lambda: (x.get_value(), f(x.get_value()), 0), color="#c0392b", radius=0.1)
        self.play(Create(line), Create(dot))
        self.next()

        self.play(x.animate.set_value(2.5), run_time=3)   # everything follows the tracker
        self.next()
