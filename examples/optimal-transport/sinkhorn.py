"""Entropic transport: with a large ε the plan is blurry and each grain goes to
the average of its many targets — the ring collapses inwards. As ε → 0 the
barycentres spread out to the ring."""
import numpy as np
from lemur.anim import Anim, FadeIn, FadeOut, MathTex, Circle
import otlib as O

A, B = O.direction(28, -125), O.direction(5, -58)
EPS = (4.0, 1.0, 0.25, 0.05)


class Sinkhorn(Anim):
    def build(self):
        fig = O.figure()
        X, Y = O.blob(A), O.ring(B)
        cols = O.colours_by_angle(X, A)
        flow = O.Flow(X)
        ghosts = O.slots(fig, Y, width=1.2)
        dots = [fig.dot(lambda i=i: flow.pos(i), color=c, radius=0.055, rim=1.6) for i, c in enumerate(cols)]
        self.add(*fig.backdrop(), *ghosts, *dots)

        label = None
        for k, eps in enumerate(EPS):
            flow.retarget(O.barycentric(O.sinkhorn(X, Y, eps), Y))
            new = MathTex(r"\varepsilon = %g" % eps, color=fig.pal.ink).scale(1.5).move_to([4.6, 3.1])
            anims = [flow.t.animate(rate_func="smooth").set_value(1.0), FadeIn(new)]
            if label is not None:
                anims.append(FadeOut(label))
            self.play(*anims, run_time=2.4 if k else 3.2)
            label = new
            self.next()
