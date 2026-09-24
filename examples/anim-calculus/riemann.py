"""Riemann sums refining to the area under a curve (midpoint rule)."""
import numpy as np
from lemur.anim import Anim, View, Create, FadeIn, FadeOut, VShape, VGroup, Text
from lemur.anim import bezier as bz


def f(x):
    return 0.3 * x ** 2 + 0.5


class Riemann(Anim):
    def build(self):
        sp = View(elev=90, static=True, viewport=(0, -0.2, 12.0, 6.4)).fit((0, 4), (0, 6))
        self.add(sp.axes(x=(0, 4, 1), y=(0, 6, 1), z=(0, 0), numbers=True, font_size=20))
        curve = sp.plot(f, 0, 4, color="#2b6cb0", stroke_width=4)
        self.play(Create(curve))
        self.next()

        def rects(n):
            g = VGroup()
            w = 4.0 / n
            for i in range(n):
                x0 = i * w
                h = f(x0 + w / 2)
                pts = [sp.point(x0, 0), sp.point(x0, h), sp.point(x0 + w, h), sp.point(x0 + w, 0), sp.point(x0, 0)]
                r = VShape(fill_color="#2b6cb0", fill_opacity=0.28, stroke_color="#1f4e79", stroke_width=1.0)
                r.set_subpaths([bz.line_handles(np.array(pts))], [True])
                g.add(r)
            return g

        group, lbl = rects(4), Text("n = 4", font_size=34, color="#5f6368").move_to(sp.point(3.2, 5.3))
        self.play(FadeIn(group), FadeIn(lbl))
        self.next()
        for n in (8, 16, 32):
            new = rects(n)
            nlbl = Text(f"n = {n}", font_size=34, color="#5f6368").move_to(sp.point(3.2, 5.3))
            self.play(FadeOut(group), FadeOut(lbl), FadeIn(new), FadeIn(nlbl), run_time=0.7)
            group, lbl = new, nlbl
            self.next()
