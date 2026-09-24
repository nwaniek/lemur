"""On a curved surface, a vector lives in the tangent space T_pS — the plane
touching the sphere at p."""
import numpy as np
from lemur.anim import Anim, View, FadeIn, Circle, MathTex
import geom

P = geom.norm([0.72, 0.32, 0.62])


class Tangent(Anim):
    def build(self):
        view = View(azim=-50, elev=20, scale=2.5, viewport=(-1.4, -0.2, 10.0, 7.2))
        sph = geom.sphere(view)
        e1, e2 = geom.tangent_basis(P)
        s = 0.85
        corners = [P + s * e1 + s * e2, P - s * e1 + s * e2, P - s * e1 - s * e2, P + s * e1 - s * e2]
        plane = view.polygon(corners, fill_color="#2b6cb0", fill_opacity=0.16,
                             color="#2b6cb0", stroke_width=1.5)
        dot = Circle(radius=0.055, fill_color="#1f4e79", fill_opacity=1.0, stroke_width=0)
        dot.move_to(view.project(P))
        vec = geom.vector(view, lambda: (P, 0.9 * e1 + 0.35 * e2), color="#c0392b")

        pl = MathTex(r"T_pS", color="#2b6cb0").move_to(view.project(P + 1.2 * e1 - 1.0 * e2))
        vl = MathTex(r"v", color="#c0392b").move_to(view.project(P + 0.55 * e1 + 0.55 * e2) + [0.35, 0.15])

        self.add(sph)
        self.play(FadeIn(sph), FadeIn(dot))
        self.next()
        self.play(FadeIn(plane), FadeIn(pl))          # the tangent plane
        self.next()
        self.play(FadeIn(vec), FadeIn(vl))            # a tangent vector
        self.next()
