"""Sphere tracing, drawn at build time: a ray leaves the eye; at each point the
signed distance f(p) to the nearest surface is a radius that is *safe* to step
— the circle of that radius touches the scene but never crosses it. The steps
shrink where the ray squeezes past things, grow in open space, and stop at the
wall when f(p) < ε."""
import numpy as np
from lemur.anim import (Anim, Create, FadeIn, GrowFromCenter, Circle, Dot, Line, DashedLine,
                        RoundedRectangle, MathTex)

INK, DIM = "#e6edf3", "#8b98a5"
TEAL, GOLD, ROSE, VIOLET = "#6ef3b4", "#ffd166", "#ff6b8b", "#b48ee0"

DISCS = [(np.array([-1.3, 1.45]), 0.6), (np.array([2.3, 1.3]), 1.0)]
BOX_C, BOX_H = np.array([2.6, -1.55]), np.array([1.2, 0.5])
WALL = 6.0
EYE = np.array([-4.4, -0.35])
DIR = np.array([1.0, 0.04]) / np.linalg.norm([1.0, 0.04])


def sdf(p):
    d = min(np.linalg.norm(p - c) - r for c, r in DISCS)
    q = np.abs(p - BOX_C) - BOX_H
    d = min(d, np.linalg.norm(np.maximum(q, 0.0)) + min(max(q[0], q[1]), 0.0))
    return min(d, WALL - p[0])


def trace(o, d, n=20, eps=0.02):
    pts, t = [], 0.0
    for _ in range(n):
        p = o + t * d
        r = sdf(p)
        pts.append((p, r))
        if r < eps:
            break
        t += r
    return pts


class SphereTrace(Anim):
    def build(self):
        scene = [Circle(radius=r, stroke_color=TEAL, stroke_width=4, fill_color=TEAL, fill_opacity=0.12).move_to(c)
                 for c, r in DISCS]
        scene.append(RoundedRectangle(width=2 * BOX_H[0], height=2 * BOX_H[1], radius=0.02, color=VIOLET,
                                      stroke_width=4, fill_color=VIOLET, fill_opacity=0.12).move_to(BOX_C))
        scene.append(Line([WALL, -3.4], [WALL, 3.4], color=TEAL, stroke_width=6))
        eye = Dot(EYE, radius=0.12, color=GOLD)
        eye_l = MathTex(r"\text{eye}", color=DIM).scale(1.2).next_to(eye, [0, -1])
        self.play(*[FadeIn(m) for m in scene], GrowFromCenter(eye), FadeIn(eye_l), run_time=1.2)
        self.next()

        ray = DashedLine(EYE, EYE + DIR * 10.8, color=DIM, stroke_width=2.4)
        self.play(Create(ray), run_time=0.8)
        self.next()

        steps = trace(EYE, DIR)
        for k, (p, r) in enumerate(steps):
            c = Circle(radius=max(r, 0.03), stroke_color=GOLD, stroke_width=2.6).move_to(p)
            c.set_stroke(opacity=0.8)
            self.play(GrowFromCenter(c), FadeIn(Dot(p, radius=0.07, color=GOLD)), run_time=0.5 if k < 3 else 0.28)
            if k == 0:
                lab = MathTex(r"f(p_0)", color=GOLD).scale(1.2).move_to(p + np.array([0.0, r + 0.35]))
                self.play(FadeIn(lab), run_time=0.3)
            if k in (0, 4, 8):
                self.next()
        end = steps[-1][0]
        tag = MathTex(r"f < \varepsilon:\ \text{hit}", color=ROSE).scale(1.2).move_to(np.array([4.9, -2.75]))
        self.play(GrowFromCenter(Dot(end, radius=0.13, color=ROSE)), FadeIn(tag), run_time=0.6)
        self.next()
