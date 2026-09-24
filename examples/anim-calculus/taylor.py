"""Taylor series: polynomials converging to sin x. A 2D plot = a top-down View."""
import numpy as np
from lemur.anim import Anim, View, Create, FadeIn, Transform, MathTex


class Taylor(Anim):
    def build(self):
        sp = View(elev=90, static=True, viewport=(0, -0.3, 12.6, 6.2)).fit((-5, 5), (-2.5, 2.5))
        self.add(sp.axes(x=(-5, 5, 1), y=(-2.5, 2.5, 1), z=(0, 0), numbers=True, font_size=20))
        sinc = sp.plot(np.sin, -5, 5, color="#9aa0a6", stroke_width=3)
        self.play(Create(sinc))
        self.next()

        terms = [
            (lambda x: x, r"\sin x \approx x"),
            (lambda x: x - x**3 / 6, r"\sin x \approx x - \tfrac{x^3}{3!}"),
            (lambda x: x - x**3 / 6 + x**5 / 120, r"\sin x \approx x - \tfrac{x^3}{3!} + \tfrac{x^5}{5!}"),
            (lambda x: x - x**3 / 6 + x**5 / 120 - x**7 / 5040,
             r"\sin x \approx x - \tfrac{x^3}{3!} + \tfrac{x^5}{5!} - \tfrac{x^7}{7!}"),
        ]
        approx = sp.plot(terms[0][0], -5, 5, color="#2b6cb0", stroke_width=3.5)
        label = MathTex(terms[0][1], color="#2b6cb0").scale(1.1).move_to(sp.point(0, 2.9))
        self.play(Create(approx), FadeIn(label))
        self.next()
        for fn, tex in terms[1:]:
            new = sp.plot(fn, -5, 5, color="#2b6cb0", stroke_width=3.5)
            nlab = MathTex(tex, color="#2b6cb0").scale(1.1).move_to(sp.point(0, 2.9))
            self.play(Transform(approx, new), Transform(label, nlab))
            self.next()
