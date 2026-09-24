"""An orbiting wireframe surface — a decaying ripple z = cos r · e^{-r²}."""
import numpy as np
from lemur.anim import Anim, View, Create


def ripple(u, v):
    r = np.hypot(u, v)
    return (u, v, 2.0 * np.cos(1.4 * r) * np.exp(-r * r / 10.0))


class Ripple(Anim):
    def build(self):
        sp = View(azim=30, elev=58, scale=0.95)
        surf = sp.surface(ripple, (-3.2, 3.2), (-3.2, 3.2),
                          u_lines=11, v_lines=11, samples=18,
                          color="#2b6cb0", stroke_width=1.1)
        self.play(Create(surf), run_time=2.5)          # draw the mesh on
        self.next()
        self.play(*sp.reorient(elev=26, azim=95), run_time=3.5)   # orbit it
        self.next()
