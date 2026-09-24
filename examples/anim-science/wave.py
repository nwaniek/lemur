import numpy as np
from lemur.anim import Anim, Circle, Line, Create, ValueTracker, VShape, Text
from lemur.anim import bezier as bz

R = 1.3
CX = -4.2            # circle centre x
X0 = -2.3            # where the wave (and its time axis) starts
XS = 0.60            # x-units per radian
TMAX = 4 * np.pi     # two periods


class CircleToSine(Anim):
    def build(self):
        # arc length along the sine, so Create's drawn tip lands on the marker
        phi = np.linspace(0, TMAX, 3000)
        ds = np.hypot(XS, R * np.cos(phi))
        s = np.concatenate([[0.0], np.cumsum((ds[:-1] + ds[1:]) / 2 * np.diff(phi))])
        S = s[-1]

        # `prog` is LINEAR in time and drives the angle → the circle turns at a
        # constant rate; Create draws by arc length (a rate_func) so its tip still
        # meets the marker, which sits at the same (uniform) angle.
        prog = ValueTracker(0.0)
        angle = lambda: prog.get_value() * TMAX
        draw_rate = lambda a: float(np.interp(a * TMAX, phi, s)) / S

        circ = VShape(color="#9aa0a6", stroke_width=2)
        a = np.linspace(0, 2 * np.pi, 160)
        circ.set_subpaths([bz.line_handles(np.c_[CX + R * np.cos(a), R * np.sin(a)])], [True])
        axis = Line([X0, 0], [X0 + TMAX * XS + 0.3, 0], color="#9aa0a6", stroke_width=1.5)

        wave = VShape(color="#2b6cb0", stroke_width=3)          # static full sine, drawn on
        wave.set_subpaths([bz.line_handles(np.c_[X0 + phi[::6] * XS, R * np.sin(phi[::6])])], [False])

        def driven(color, w, fn):
            m = VShape(color=color, stroke_width=w)
            m.add_updater(lambda mob: mob.set_subpaths(
                [bz.line_handles(np.asarray(fn(angle()), float))], [False]))
            return m

        radius = driven("#c0392b", 2.5, lambda t: [[CX, 0], [CX + R * np.cos(t), R * np.sin(t)]])
        connect = driven("#c0392b", 1.2, lambda t: [[CX + R * np.cos(t), R * np.sin(t)],
                                                     [X0 + t * XS, R * np.sin(t)]])

        def marker(color, fn):
            d = Circle(radius=0.08, fill_color=color, fill_opacity=1.0, stroke_width=0)
            d.add_updater(lambda m: m.move_to(fn(angle())))
            return d

        dot = marker("#c0392b", lambda t: [CX + R * np.cos(t), R * np.sin(t)])
        head = marker("#2b6cb0", lambda t: [X0 + t * XS, R * np.sin(t)])
        lbl = Text("sin θ", font_size=30, color="#2b6cb0").move_to([X0 + TMAX * XS * 0.5, R + 0.9])

        self.add(circ, axis, radius, connect, dot, head, lbl)
        self.play(Create(wave, rate_func=draw_rate),
                  prog.animate(rate_func="linear").set_value(1.0), run_time=6)
        self.next()
