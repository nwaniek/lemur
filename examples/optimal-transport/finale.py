"""The same sand, reshaped again and again — each leg the optimal plan from the
current cloud to the next shape — while the camera drifts round the globe."""
import numpy as np
from lemur.anim import Anim, FadeIn
import otlib as O

C = O.direction(20, -90)
SHAPES = [O.ring(C, radius=0.85), O.two_blobs(C), O.spiral(C), O.heart(C), O.blob(C, sigma=0.3)]


class Finale(Anim):
    def build(self):
        fig = O.figure(azim=0, elev=16, scale=1.7)
        X = O.blob(C, sigma=0.3)
        cols = O.colours_by_angle(X, C)
        flow = O.Flow(X)
        dots = [fig.dot(lambda i=i: flow.pos(i), color=c, radius=0.055, rim=1.6) for i, c in enumerate(cols)]
        self.add(*fig.backdrop(), *dots)

        azims = [20, -20, 12, -12, 0]
        for Y, az in zip(SHAPES, azims):
            cur = np.array([flow.pos(i) for i in range(O.N)])
            flow.retarget(Y[O.monge(cur, Y)])
            self.play(flow.t.animate(rate_func="smooth").set_value(1.0),
                      *fig.view.reorient(azim=az, elev=16 + 10 * np.sin(np.radians(az))), run_time=2.6)
            self.next()
