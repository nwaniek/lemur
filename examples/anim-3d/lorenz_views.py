"""One attractor, four views. Each view is a camera (angle) + a viewport (a rect
it draws into and is clipped to) — so the main plot and the insets are made with
exactly the same code, just a different viewport. Frames, axes and legend appear
first (empty); then the trajectory is drawn in every view at once, a marker
riding its head — the same 3D point everywhere."""
import numpy as np
from lemur.anim import Anim, View, Create, FadeIn, ValueTracker, VGroup, legend, panel

BLUE, RED = "#2b6cb0", "#c0392b"


def integrate(n=3000, dt=0.008, s=10.0, r=28.0, b=8.0 / 3.0):
    p = np.empty((n, 3)); p[0] = (0.1, 0.0, 1.05)
    for i in range(1, n):
        x, y, z = p[i - 1]
        p[i] = p[i - 1] + dt * np.array([s * (y - x), x * (r - z) - y, x * y - b * z])
    return p[400:]                                    # drop the transient


class LorenzViews(Anim):
    def build(self):
        P = integrate(); P = P - P.mean(0); P = P / np.abs(P).max() * 2.5
        Q = P[::2]                                    # lighter copy for the insets
        prog = ValueTracker(0.0)

        main = View(azim=-8, elev=14, scale=1.2, viewport=(-2.8, 0, 8.6, 7.6))
        m_axes = main.axes(x=2.6, y=2.6, z=2.6)
        m_labels = VGroup(main.label("x", [3.0, 0, 0], font_size=24, color="#5f6368"),
                          main.label("y", [0, 3.0, 0], font_size=24, color="#5f6368"),
                          main.label("z", [0, 0, 3.0], font_size=24, color="#5f6368"))
        m_curve = main.curve(P, color=BLUE, stroke_width=1.4)

        PW, PH = 3.2, 2.0
        R = (-2, 2, 1)                                # numbered range on each in-plane axis
        specs = [("top  (x–y)", 0, 90, (4.4, 2.4), dict(x=R, y=R, z=2.0)),
                 ("front (x–z)", 0, 6, (4.4, 0.0), dict(x=R, y=2.0, z=R)),
                 ("side  (y–z)", 90, 6, (4.4, -2.4), dict(x=2.0, y=R, z=R))]
        frames, in_axes, in_curves, dots = VGroup(), VGroup(), [], \
            [main.trace_dot(P, prog, color=RED, radius=0.11, by="index")]
        for lab, az, el, ctr, axspec in specs:
            v = View(azim=az, elev=el, scale=0.42, viewport=(ctr[0], ctr[1], PW, PH))
            frames.add(panel(ctr[0], ctr[1], PW, PH, lab))
            in_axes.add(v.axes(numbers=True, font_size=13, tick=0.05, stroke_width=1.1, **axspec))
            in_curves.append((v, v.curve(Q, color=BLUE, stroke_width=0.9)))
            dots.append(v.trace_dot(Q, prog, color=RED, radius=0.055, by="index"))

        leg = legend([(BLUE, "trajectory"), (RED, "current state", "dot")], (-6.4, 3.4))

        # 1) all views + axes + legend appear, empty (no trajectory yet)
        self.play(FadeIn(m_axes), FadeIn(m_labels), FadeIn(frames), FadeIn(in_axes), FadeIn(leg))
        self.next()
        # 2) draw the trajectory in every view at once, the marker riding its head
        self.play(Create(m_curve, rate_func=main.rate(P)),
                  *[Create(c, rate_func=v.rate(Q)) for v, c in in_curves],
                  *[FadeIn(d) for d in dots],
                  prog.animate(rate_func="linear").set_value(1.0), run_time=7)
        self.next()
