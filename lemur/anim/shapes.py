"""Geometric primitives.

All of these are plain :class:`~lemur.anim.mobject.VShape` shapes, so they morph into
one another, can be drawn progressively, and carry the usual paint options.
"""

from __future__ import annotations

import numpy as np

from . import bezier as bz
from . import constants as C
from .color import to_color
from .mobject import Shape, VGroup, VShape

__all__ = [
    "Arc",
    "Circle",
    "Ellipse",
    "Dot",
    "Annulus",
    "Sector",
    "Line",
    "DashedLine",
    "Polyline",
    "Polygon",
    "RegularPolygon",
    "Triangle",
    "Rectangle",
    "Square",
    "RoundedRectangle",
    "Arrow",
    "DoubleArrow",
    "Vector",
    "ArrowTip",
    "Elbow",
    "Angle",
    "RightAngle",
    "Brace",
    "SurroundingRectangle",
    "BackgroundRectangle",
    "Underline",
    "Cross",
    "CurvedArrow",
]

#: Control-point offset that makes a cubic match a circular arc of 90 degrees.
_KAPPA = 4 * (np.sqrt(2) - 1) / 3


# --------------------------------------------------------------------------
# arcs and circles
# --------------------------------------------------------------------------


def arc_points(radius: float, start_angle: float, angle: float, center=C.ORIGIN) -> np.ndarray:
    """``3k+1`` cubic points approximating a circular arc.

    Split so no segment exceeds 90 degrees, which keeps the maximum radial
    error below ~2.7e-4 * radius -- invisible at any sane zoom.
    """
    center = np.asarray(center, dtype=float)
    n = max(1, int(np.ceil(abs(angle) / (C.PI / 2) - 1e-9)))
    d = angle / n
    # Handle length for a cubic spanning `d` radians on the unit circle.
    h = 4 / 3 * np.tan(d / 4)
    pts = [np.array([np.cos(start_angle), np.sin(start_angle)])]
    for i in range(n):
        a0 = start_angle + i * d
        a1 = a0 + d
        p0 = np.array([np.cos(a0), np.sin(a0)])
        p1 = np.array([np.cos(a1), np.sin(a1)])
        t0 = np.array([-np.sin(a0), np.cos(a0)])
        t1 = np.array([-np.sin(a1), np.cos(a1)])
        pts.extend([p0 + h * t0, p1 - h * t1, p1])
    return np.array(pts) * radius + center


class Arc(VShape):
    def __init__(self, radius: float = 1.0, start_angle: float = 0.0, angle: float = C.PI / 2, arc_center=C.ORIGIN, **kw):
        super().__init__(**kw)
        self.radius = radius
        self.arc_center = np.asarray(arc_center, dtype=float)
        self.set_subpaths([arc_points(radius, start_angle, angle, arc_center)], [False])


class Circle(VShape):
    def __init__(self, radius: float = 1.0, center=C.ORIGIN, **kw):
        kw.setdefault("stroke_color", kw.get("color", C.RED))   # an explicit color= sets the stroke
        super().__init__(**kw)
        self.radius = radius
        self.set_subpaths([arc_points(radius, 0.0, C.TAU, center)], [True])

    @staticmethod
    def around(mobject: Shape, buff: float = C.MED_SMALL_BUFF, **kw) -> "Circle":
        """A circle that encloses ``mobject``."""
        lo, hi = mobject.get_bbox()
        r = float(np.linalg.norm(hi - lo) / 2) + buff
        return Circle(r, **kw).move_to(mobject.get_center())


class Ellipse(VShape):
    def __init__(self, width: float = 2.0, height: float = 1.0, center=C.ORIGIN, **kw):
        super().__init__(**kw)
        pts = arc_points(1.0, 0.0, C.TAU)
        pts = pts * np.array([width / 2, height / 2]) + np.asarray(center, dtype=float)
        self.set_subpaths([pts], [True])


class Dot(VShape):
    def __init__(self, point=C.ORIGIN, radius: float = C.DEFAULT_DOT_RADIUS, **kw):
        kw.setdefault("color", C.WHITE)
        kw.setdefault("fill_opacity", 1.0)
        kw.setdefault("stroke_width", 0.0)
        super().__init__(**kw)
        self.radius = radius
        self.set_subpaths([arc_points(radius, 0.0, C.TAU, point)], [True])


class Annulus(VShape):
    """A ring: outer circle plus a reversed inner circle (even-odd fill)."""

    def __init__(self, inner_radius: float = 0.6, outer_radius: float = 1.0, center=C.ORIGIN, **kw):
        kw.setdefault("fill_opacity", 1.0)
        kw.setdefault("stroke_width", 0.0)
        super().__init__(**kw)
        outer = arc_points(outer_radius, 0.0, C.TAU, center)
        inner = arc_points(inner_radius, 0.0, -C.TAU, center)
        self.set_subpaths([outer, inner], [True, True])


class Sector(VShape):
    def __init__(self, radius: float = 1.0, start_angle: float = 0.0, angle: float = C.PI / 2, center=C.ORIGIN, **kw):
        kw.setdefault("fill_opacity", 1.0)
        super().__init__(**kw)
        c = np.asarray(center, dtype=float)
        arc = arc_points(radius, start_angle, angle, c)
        pts = np.vstack([c[None, :], bz.line_handles(np.array([c, arc[0]]))[1:], arc[1:]])
        pts = np.vstack([pts, bz.line_handles(np.array([arc[-1], c]))[1:]])
        self.set_subpaths([pts], [True])


# --------------------------------------------------------------------------
# lines and polygons
# --------------------------------------------------------------------------


class Line(VShape):
    def __init__(self, start=C.LEFT, end=C.RIGHT, buff: float = 0.0, path_arc: float = 0.0, **kw):
        super().__init__(**kw)
        self.set_start_end(start, end, buff, path_arc)

    def set_start_end(self, start, end, buff: float = 0.0, path_arc: float = 0.0) -> "Line":
        p = _anchor(start, end)
        q = _anchor(end, start)
        if buff:
            d = q - p
            n = np.linalg.norm(d)
            if n > 2 * buff:
                u = d / n
                p, q = p + u * buff, q - u * buff
        if abs(path_arc) > 1e-9:
            self.set_subpaths([_arc_between(p, q, path_arc)], [False])
        else:
            self.set_subpaths([bz.line_handles(np.array([p, q]))], [False])
        return self

    def get_vector(self) -> np.ndarray:
        return self.get_end() - self.get_start()

    def get_angle(self) -> float:
        v = self.get_vector()
        return float(np.arctan2(v[1], v[0]))

    def get_length(self) -> float:
        return float(np.linalg.norm(self.get_vector()))

    def get_unit_vector(self) -> np.ndarray:
        v = self.get_vector()
        n = np.linalg.norm(v)
        return v / n if n > 1e-12 else np.array([1.0, 0.0])

    def get_normal(self) -> np.ndarray:
        u = self.get_unit_vector()
        return np.array([-u[1], u[0]])


def _arc_between(p: np.ndarray, q: np.ndarray, angle: float) -> np.ndarray:
    """Circular arc from ``p`` to ``q`` subtending ``angle`` radians."""
    chord = q - p
    L = np.linalg.norm(chord)
    if L < 1e-12:
        return bz.line_handles(np.array([p, q]))
    r = L / (2 * np.sin(angle / 2))
    mid = (p + q) / 2
    normal = np.array([-chord[1], chord[0]]) / L
    center = mid + normal * r * np.cos(angle / 2)
    a0 = np.arctan2(*(p - center)[::-1])
    return arc_points(float(np.linalg.norm(p - center)), float(a0), angle, center)


class DashedLine(Line):
    def __init__(self, start=C.LEFT, end=C.RIGHT, dash_length: float = 0.12, gap: float | None = None, **kw):
        super().__init__(start, end, **kw)
        self.dash = [dash_length, gap if gap is not None else dash_length * 0.8]


class Polyline(VShape):
    def __init__(self, *points, smooth: bool = False, **kw):
        super().__init__(**kw)
        pts = _points_arg(points)
        if smooth:
            self.set_points_smoothly(pts)
        else:
            self.set_points_as_corners(pts)


class Polygon(VShape):
    def __init__(self, *points, smooth: bool = False, **kw):
        super().__init__(**kw)
        pts = _points_arg(points)
        if smooth:
            self.set_points_smoothly(pts, close=True)
        else:
            self.set_points_as_corners(pts, close=True)


class RegularPolygon(Polygon):
    def __init__(self, n: int = 6, radius: float = 1.0, start_angle: float | None = None, center=C.ORIGIN, **kw):
        if start_angle is None:
            start_angle = C.PI / 2 if n % 2 else 0.0
        angles = start_angle + np.arange(n) * C.TAU / n
        pts = np.stack([np.cos(angles), np.sin(angles)], axis=1) * radius + np.asarray(center, dtype=float)
        super().__init__(pts, **kw)


class Triangle(RegularPolygon):
    def __init__(self, radius: float = 1.0, **kw):
        super().__init__(3, radius, **kw)


class Rectangle(VShape):
    def __init__(self, width: float = 2.0, height: float = 1.0, center=C.ORIGIN, **kw):
        super().__init__(**kw)
        w, h = width / 2, height / 2
        c = np.asarray(center, dtype=float)
        corners = np.array([[w, h], [-w, h], [-w, -h], [w, -h], [w, h]]) + c
        self.set_points_as_corners(corners, close=True)


class Square(Rectangle):
    def __init__(self, side: float = 2.0, **kw):
        super().__init__(side, side, **kw)


class RoundedRectangle(VShape):
    def __init__(self, width: float = 2.0, height: float = 1.0, radius: float = 0.2, center=C.ORIGIN, **kw):
        super().__init__(**kw)
        w, h = width / 2, height / 2
        r = float(min(radius, w, h))
        c = np.asarray(center, dtype=float)
        # corner centres, counter-clockwise from the +x/+y one
        centres = [np.array([w - r, h - r]), np.array([-w + r, h - r]), np.array([-w + r, -h + r]), np.array([w - r, -h + r])]
        pts: list[np.ndarray] = []
        for i, cc in enumerate(centres):
            arc = arc_points(r, C.PI / 2 * i, C.PI / 2, cc + c)
            if pts:
                pts.extend(bz.line_handles(np.array([pts[-1], arc[0]]))[1:])
                pts.extend(arc[1:])
            else:
                pts.extend(arc)
        pts.extend(bz.line_handles(np.array([pts[-1], pts[0]]))[1:])
        self.set_subpaths([np.array(pts)], [True])


# --------------------------------------------------------------------------
# arrows
# --------------------------------------------------------------------------


class ArrowTip(VShape):
    """A filled triangular tip, pointing along +x before being placed."""

    def __init__(self, length: float = C.DEFAULT_ARROW_TIP_LENGTH, width: float | None = None, **kw):
        kw.setdefault("fill_opacity", 1.0)
        kw.setdefault("stroke_width", 0.0)
        super().__init__(**kw)
        w = (width if width is not None else length * 0.85) / 2
        self.set_points_as_corners([[0, 0], [-length, w], [-length * 0.75, 0], [-length, -w]], close=True)

    def point_at(self, position, angle: float) -> "ArrowTip":
        self.rotate(angle, about_point=C.ORIGIN)
        return self.shift(np.asarray(position, dtype=float))


class Arrow(VGroup):
    """A line with a tip.  ``buff`` shortens both ends (handy between shapes)."""

    def __init__(
        self,
        start=C.LEFT,
        end=C.RIGHT,
        buff: float = 0.0,
        tip_length: float | None = None,
        tip_at_start: bool = False,
        path_arc: float = 0.0,
        **kw,
    ):
        color = kw.pop("color", C.WHITE)
        stroke_width = kw.pop("stroke_width", C.DEFAULT_STROKE_WIDTH)
        super().__init__(**kw)
        self.path_arc = path_arc
        self.line = Line(start, end, buff=buff, path_arc=path_arc, color=color, stroke_width=stroke_width)
        L = self.line.get_length()
        tl = tip_length if tip_length is not None else float(np.clip(L * 0.25, 0.12, 0.35))
        self.tips: list[ArrowTip] = []
        self.add(self.line)
        for at_start in ([True, False] if tip_at_start == "both" else [tip_at_start]):
            tip = ArrowTip(tl, color=color)
            if at_start:
                d = -self.line.get_unit_vector()
                tip.point_at(self.line.get_start(), float(np.arctan2(d[1], d[0])))
            else:
                d = self.line.get_unit_vector()
                tip.point_at(self.line.get_end(), float(np.arctan2(d[1], d[0])))
            self.tips.append(tip)
            self.add(tip)
        # Pull the shaft back so it does not poke through a translucent tip.
        self._trim_shaft(tl, tip_at_start)

    def _trim_shaft(self, tip_length: float, tip_at_start) -> None:
        if abs(self.path_arc) > 1e-9:
            return  # the straight-line inset below would flatten the arc
        p, q = self.line.get_start(), self.line.get_end()
        u = self.line.get_unit_vector()
        inset = tip_length * 0.7
        if self.line.get_length() > 2.2 * inset:
            new_p = p + u * inset if tip_at_start in (True, "both") else p
            new_q = q - u * inset if tip_at_start in (False, "both") else q
            self.line.set_start_end(new_p, new_q)

    def get_start(self):
        return self.line.get_start()

    def get_end(self):
        return self.tips[-1].get_center() if self.tips else self.line.get_end()


class DoubleArrow(Arrow):
    def __init__(self, start=C.LEFT, end=C.RIGHT, **kw):
        super().__init__(start, end, tip_at_start="both", **kw)


class Vector(Arrow):
    def __init__(self, direction=C.RIGHT, origin=C.ORIGIN, **kw):
        o = np.asarray(origin, dtype=float)
        super().__init__(o, o + np.asarray(direction, dtype=float), **kw)


class CurvedArrow(Arrow):
    def __init__(self, start, end, angle: float = C.PI / 3, **kw):
        super().__init__(start, end, path_arc=angle, **kw)


# --------------------------------------------------------------------------
# annotation
# --------------------------------------------------------------------------


class Elbow(VShape):
    def __init__(self, size: float = 0.25, angle: float = 0.0, **kw):
        super().__init__(**kw)
        self.set_points_as_corners([[0, size], [0, 0], [size, 0]])
        self.rotate(angle, about_point=C.ORIGIN)


class Angle(VShape):
    """An arc marking the angle between two lines."""

    def __init__(self, line1: Line, line2: Line, radius: float = 0.5, quadrant=(1, 1), **kw):
        kw.setdefault("stroke_width", 2.5)
        super().__init__(**kw)
        a1, a2 = line1.get_angle(), line2.get_angle()
        if quadrant[0] < 0:
            a1 += C.PI
        if quadrant[1] < 0:
            a2 += C.PI
        delta = (a2 - a1 + C.PI) % C.TAU - C.PI
        vertex = _line_intersection(line1, line2)
        self.set_subpaths([arc_points(radius, a1, delta, vertex)], [False])
        self.vertex = vertex


class RightAngle(Elbow):
    def __init__(self, line1: Line, line2: Line, size: float = 0.25, quadrant=(1, 1), **kw):
        super().__init__(size, **kw)
        v = _line_intersection(line1, line2)
        self.rotate(line1.get_angle(), about_point=C.ORIGIN)
        if quadrant[0] < 0 or quadrant[1] < 0:
            self.rotate(C.PI if quadrant[0] < 0 and quadrant[1] < 0 else C.PI / 2, about_point=C.ORIGIN)
        self.shift(v)


def _line_intersection(l1: Line, l2: Line) -> np.ndarray:
    p, r = l1.get_start(), l1.get_vector()
    q, s = l2.get_start(), l2.get_vector()
    denom = r[0] * s[1] - r[1] * s[0]
    if abs(denom) < 1e-12:
        return (p + q) / 2
    t = ((q[0] - p[0]) * s[1] - (q[1] - p[1]) * s[0]) / denom
    return p + t * r


class Brace(VShape):
    """A curly brace spanning ``mobject`` on the given side."""

    def __init__(self, mobject: Shape, direction=C.DOWN, buff: float = 0.15, sharpness: float = 1.0, **kw):
        kw.setdefault("fill_opacity", 1.0)
        kw.setdefault("stroke_width", 0.0)
        super().__init__(**kw)
        d = np.asarray(direction, dtype=float)
        d = d / np.linalg.norm(d)
        # _brace_path points DOWN; this is the rotation that aims it at `d`.
        angle = float(np.arctan2(d[1], d[0])) + C.PI / 2

        lo, hi = mobject.get_bbox()
        # Length measured perpendicular to `direction`.
        perp = np.array([-d[1], d[0]])
        corners = np.array([[lo[0], lo[1]], [hi[0], lo[1]], [lo[0], hi[1]], [hi[0], hi[1]]])
        proj = corners @ perp
        length = float(proj.max() - proj.min())

        self.set_subpaths([_brace_path(length, sharpness)], [True])
        self.rotate(angle, about_point=C.ORIGIN)
        self.next_to(mobject, d, buff=buff)
        self.direction = d

    def put_at_tip(self, mobject: Shape, buff: float = 0.15) -> Shape:
        """Place ``mobject`` just beyond the brace's point."""
        return mobject.next_to(self.get_tip(), self.direction, buff=buff)

    def get_tip(self) -> np.ndarray:
        return self.get_corner(self.direction)


def _brace_centerline(length: float, curl: float) -> tuple[np.ndarray, np.ndarray]:
    """Densely sampled points + unit tangents of a down-pointing brace spine.

    The spine is two shoulders and a central spike, built from exact quarter
    arcs and straight arms, then resampled uniformly by arc length so the
    thickness profile below is geometric rather than parametric.
    """
    r = float(min(curl, length / 4))
    L = length / 2

    def arc(cx, cy, a0, a1, n):
        th = np.linspace(a0, a1, n)
        pts = np.stack([cx + r * np.cos(th), cy + r * np.sin(th)], axis=1)
        sign = 1.0 if a1 > a0 else -1.0
        tan = np.stack([-np.sin(th), np.cos(th)], axis=1) * sign
        return pts, tan

    def seg(p, q, n):
        t = np.linspace(0, 1, n)[:, None]
        pts = np.asarray(p) + (np.asarray(q) - np.asarray(p)) * t
        d = np.asarray(q) - np.asarray(p)
        d = d / max(np.linalg.norm(d), 1e-12)
        return pts, np.repeat(d[None, :], n, axis=0)

    arm = max(2, int(60 * max(L - 2 * r, 1e-3) / max(L, 1e-3)))
    pieces = [
        arc(-L + r, 0.0, C.PI, 1.5 * C.PI, 24),  # left shoulder
        seg((-L + r, -r), (-r, -r), arm),  # left arm
        arc(-r, -2 * r, 0.5 * C.PI, 0.0, 24),  # into the spike
        arc(r, -2 * r, C.PI, 0.5 * C.PI, 24),  # out of the spike
        seg((r, -r), (L - r, -r), arm),  # right arm
        arc(L - r, 0.0, 1.5 * C.PI, 2 * C.PI, 24),  # right shoulder
    ]
    pts = np.vstack([p for p, _ in pieces])
    tan = np.vstack([t for _, t in pieces])
    # Drop duplicated join points.
    keep = np.concatenate([[True], np.linalg.norm(np.diff(pts, axis=0), axis=1) > 1e-9])
    return pts[keep], tan[keep]


def _brace_path(length: float, sharpness: float = 1.0) -> np.ndarray:
    """A downward-pointing curly brace of the given horizontal span.

    Built as a variable-width offset of the spine.  The width vanishes at both
    ends and at the spike, which is what makes it read as a typographic brace
    rather than a bent pipe.
    """
    curl = min(0.18, length / 5)
    spine, tan = _brace_centerline(length, curl)
    normal = np.stack([-tan[:, 1], tan[:, 0]], axis=1)

    # Arc-length parameter, so the taper is geometric.
    d = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(spine, axis=0), axis=1))])
    s = d / max(d[-1], 1e-12)

    half_w = 0.5 * 0.13 * sharpness * np.abs(np.sin(C.TAU * s)) ** 0.4
    left = spine + normal * half_w[:, None]
    right = spine - normal * half_w[:, None]

    outline = np.vstack([left, right[::-1]])
    return bz.catmull_rom_handles(outline, closed=True)


class SurroundingRectangle(RoundedRectangle):
    def __init__(self, mobject: Shape, buff: float = C.MED_SMALL_BUFF, corner_radius: float = 0.1, **kw):
        kw.setdefault("stroke_color", kw.get("color", C.YELLOW))   # an explicit color= sets the stroke
        lo, hi = mobject.get_bbox()
        size = hi - lo + 2 * buff
        super().__init__(float(size[0]), float(size[1]), corner_radius, **kw)
        self.move_to((lo + hi) / 2)


class BackgroundRectangle(Rectangle):
    """An opaque plate behind ``mobject``, e.g. to lift text off a plot."""

    def __init__(self, mobject: Shape, buff: float = 0.08, color=C.BLACK, opacity: float = 0.85, **kw):
        lo, hi = mobject.get_bbox()
        size = hi - lo + 2 * buff
        kw.setdefault("stroke_width", 0.0)
        super().__init__(float(size[0]), float(size[1]), fill_color=color, fill_opacity=opacity, **kw)
        self.move_to((lo + hi) / 2)
        self.z_index = mobject.z_index - 0.5


class Underline(Line):
    def __init__(self, mobject: Shape, buff: float = 0.1, **kw):
        lo, hi = mobject.get_bbox()
        super().__init__([lo[0], lo[1] - buff], [hi[0], lo[1] - buff], **kw)


class Cross(VGroup):
    def __init__(self, mobject: Shape | None = None, size: float = 1.0, **kw):
        kw.setdefault("stroke_color", kw.get("color", C.RED))   # an explicit color= sets the stroke
        kw.setdefault("stroke_width", 6.0)
        super().__init__(**kw)
        s = size / 2
        style = {k: v for k, v in kw.items() if k.startswith("stroke")}
        self.add(Line([-s, -s], [s, s], **style), Line([-s, s], [s, -s], **style))
        if mobject is not None:
            lo, hi = mobject.get_bbox()
            self.set_width(float(hi[0] - lo[0]) * 1.1)
            self.set_height(float(hi[1] - lo[1]) * 1.1, stretch=True)
            self.move_to(mobject.get_center())


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------


def _anchor(value, toward) -> np.ndarray:
    """Resolve a point argument that may be a mobject (use its near edge)."""
    if isinstance(value, Shape):
        other = _anchor(toward, C.ORIGIN) if not isinstance(toward, Shape) else toward.get_center()
        direction = other - value.get_center()
        n = np.linalg.norm(direction)
        return value.get_corner(direction / n if n > 1e-9 else C.ORIGIN)
    return np.asarray(value, dtype=float)


def _points_arg(points) -> np.ndarray:
    """Accept ``Polygon([a,b,c])`` as well as ``Polygon(a, b, c)``."""
    if len(points) == 1 and not np.isscalar(points[0]):
        arr = np.asarray(points[0], dtype=float)
        if arr.ndim == 2:
            return arr
    return np.array([np.asarray(p, dtype=float) for p in points])
