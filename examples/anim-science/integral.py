"""The area under a curve — a 2D plot, which is just a top-down View view."""
import numpy as np
from lemur.anim import Anim, View, Create, ValueTracker, VShape, Text
from lemur.anim import bezier as bz


def f(x):
    return 0.35 * x ** 2 - 0.08 * x ** 3 + 1.0


class Integral(Anim):
    def build(self):
        sp = View(elev=90, viewport=(0, 0, 12.0, 6.6)).fit((0, 4), (0, 3))
        axes = sp.axes(x=(0, 4, 1), y=(0, 3, 1), z=(0, 0), numbers=True, font_size=22)
        xlab = Text("x", font_size=28, color="#5f6368").move_to(sp.point(4.25, -0.28))
        ylab = Text("f(x)", font_size=28, color="#5f6368").move_to(sp.point(-0.35, 3.15))
        curve = sp.plot(f, 0, 4, color="#2b6cb0", stroke_width=4)

        self.add(axes, xlab, ylab)
        self.play(Create(curve))
        self.next()

        bound = ValueTracker(0.0)
        area = VShape(fill_color="#2b6cb0", fill_opacity=0.28, stroke_width=0)

        def sweep(m):
            xr = max(bound.get_value(), 1e-3)
            xs = np.linspace(0, xr, 80)
            pts = [sp.point(0, 0)] + [sp.point(x, f(x)) for x in xs] + [sp.point(xr, 0)]
            m.set_subpaths([bz.line_handles(np.array(pts))], [True])

        area.add_updater(sweep)
        self.add(area)
        self.play(bound.animate.set_value(4.0), run_time=3)   # the area fills in x → 4
        self.next()
