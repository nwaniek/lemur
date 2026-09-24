"""The scene graph.

:class:`Shape` ("mathematical object") is a node: a transform-able thing with
children.  :class:`VShape` adds geometry -- a list of cubic-Bézier subpaths --
and paint.  Almost everything visible in an animation is a ``VShape``.

Transforms are *baked into the points* rather than kept as a matrix on the
node.  That is what makes morphing between arbitrary shapes trivial, and the
renderer recovers a compact SVG ``transform`` afterwards where it can.
"""

from __future__ import annotations

import itertools
from typing import Callable, Iterable, Iterator, Sequence

import numpy as np

from . import bezier as bz
from . import constants as C
from .color import Color, to_color

# Foreground a shape falls back to when created without a colour. White suits a
# dark backdrop (wanim's origin); when an animation is embedded on a slide the
# emitter overrides this with the deck's foreground so default text/shapes read.
_DEFAULT_COLOR = C.WHITE


def set_default_color(color) -> None:
    """Set the fallback colour for shapes created without an explicit one."""
    global _DEFAULT_COLOR
    _DEFAULT_COLOR = color

__all__ = ["Shape", "VShape", "VGroup", "Group", "GlyphRef", "ValueTracker"]

#: Bumped whenever any mobject's points change; derived caches key off it.
_geom_counter = 0


class GlyphRef:
    """Marks a ``VShape`` as an instance of a shared glyph outline.

    The web renderer uses this to emit ``<use href="#g12">`` instead of a fresh
    path, which is what keeps a text-heavy deck small.  It is a hint only: if
    the points have been deformed non-affinely the renderer notices and falls
    back to a literal path.
    """

    __slots__ = ("key", "ref_subpaths", "ref_closed")

    def __init__(self, key: str, ref_subpaths: list[np.ndarray], ref_closed: list[bool]):
        self.key = key
        self.ref_subpaths = ref_subpaths
        self.ref_closed = ref_closed


# ==========================================================================
# Shape
# ==========================================================================


class Shape:
    """A node in the scene graph."""

    def __init__(self, *submobjects: "Shape", name: str | None = None, z_index: float = 0.0):
        self.submobjects: list[Shape] = []
        self.name = name or self.__class__.__name__
        self.z_index = z_index
        self.updaters: list[Callable] = []
        self._visible = True
        #: Ignore the camera and stay put on screen.  Slide furniture (title,
        #: page number) uses this so a zoom does not carry it off the edge.
        self.fixed_in_frame = False
        if submobjects:
            self.add(*submobjects)

    # -- tree --------------------------------------------------------------

    def add(self, *mobjects: "Shape") -> "Shape":
        for m in mobjects:
            if m is self:
                raise ValueError("cannot add a mobject to itself")
            if m not in self.submobjects:
                self.submobjects.append(m)
        return self

    def remove(self, *mobjects: "Shape") -> "Shape":
        for m in mobjects:
            if m in self.submobjects:
                self.submobjects.remove(m)
        return self

    def set_z_index(self, z: float) -> "Shape":
        self.z_index = z
        return self

    @property
    def family(self) -> list["Shape"]:
        """``self`` followed by every descendant, depth first."""
        out = [self]
        for m in self.submobjects:
            out.extend(m.family)
        return out

    def leaves(self) -> list["Shape"]:
        """Family members that actually carry geometry."""
        return [m for m in self.family if m.has_points()]

    def has_points(self) -> bool:
        return False

    def __getitem__(self, i):
        if isinstance(i, slice):
            return VGroup(*self.submobjects[i])
        return self.submobjects[i]

    def __len__(self) -> int:
        return len(self.submobjects)

    def __iter__(self) -> Iterator["Shape"]:
        return iter(self.submobjects)

    def __repr__(self) -> str:
        return f"<{self.name} n={len(self.submobjects)}>"

    # -- copying -----------------------------------------------------------

    def copy(self) -> "Shape":
        clone = self.__class__.__new__(self.__class__)
        clone.__dict__.update(self._copy_fields())
        clone.submobjects = [m.copy() for m in self.submobjects]
        return clone

    def _copy_fields(self) -> dict:
        out = {}
        for k, v in self.__dict__.items():
            if k == "submobjects":
                continue
            if isinstance(v, np.ndarray):
                out[k] = v.copy()
            elif isinstance(v, list):
                out[k] = [x.copy() if isinstance(x, np.ndarray) else x for x in v]
            elif isinstance(v, dict):
                out[k] = dict(v)
            else:
                out[k] = v
        return out

    def save_state(self) -> "Shape":
        """Remember the current state so ``Restore(mob)`` can come back to it."""
        self._saved_state = self.copy()
        return self

    def restore(self) -> "Shape":
        saved = getattr(self, "_saved_state", None)
        if saved is None:
            raise ValueError("nothing saved; call save_state() first")
        return self.become(saved)

    def become(self, other: "Shape") -> "Shape":
        """Make ``self`` a structural copy of ``other`` in place."""
        keep = self.submobjects
        saved = self.__dict__.get("_saved_state")
        self.__dict__.update(other._copy_fields())
        self.submobjects = keep
        if saved is not None:
            self._saved_state = saved  # a restore target must survive becoming
        _match_length(self.submobjects, other.submobjects)
        for a, b in zip(self.submobjects, other.submobjects):
            a.become(b)
        return self

    # -- geometry ----------------------------------------------------------

    def all_points(self) -> np.ndarray:
        """Every control point in the family, as an ``(N, 2)`` array."""
        chunks = [m._own_points() for m in self.family]
        chunks = [c for c in chunks if len(c)]
        return np.concatenate(chunks) if chunks else np.zeros((0, 2))

    def _own_points(self) -> np.ndarray:
        return np.zeros((0, 2))

    def apply_points_function(self, fn: Callable[[np.ndarray], np.ndarray]) -> "Shape":
        """Apply ``fn`` to every point array in the family."""
        for m in self.family:
            m._apply_own(fn)
        return self

    def _apply_own(self, fn) -> None:
        pass

    def get_bbox(self) -> tuple[np.ndarray, np.ndarray]:
        """Tight ``(lo, hi)`` bounding box, exact for cubic Béziers."""
        boxes = [m._own_bbox() for m in self.family]
        boxes = [b for b in boxes if b is not None]
        if not boxes:
            return np.zeros(2), np.zeros(2)
        lo = np.min([b[0] for b in boxes], axis=0)
        hi = np.max([b[1] for b in boxes], axis=0)
        return lo, hi

    def _own_bbox(self):
        return None

    # -- measurements ------------------------------------------------------

    def get_center(self) -> np.ndarray:
        lo, hi = self.get_bbox()
        return (lo + hi) / 2

    def get_corner(self, direction) -> np.ndarray:
        """Point on the bounding box in the given direction, e.g. ``UL``."""
        lo, hi = self.get_bbox()
        d = np.asarray(direction, dtype=float)
        mid = (lo + hi) / 2
        return np.where(d > 0, hi, np.where(d < 0, lo, mid))

    # Aliases that read well at call sites.
    get_edge = get_corner

    def get_left(self) -> np.ndarray:
        return self.get_corner(C.LEFT)

    def get_right(self) -> np.ndarray:
        return self.get_corner(C.RIGHT)

    def get_top(self) -> np.ndarray:
        return self.get_corner(C.UP)

    def get_bottom(self) -> np.ndarray:
        return self.get_corner(C.DOWN)

    @property
    def width(self) -> float:
        lo, hi = self.get_bbox()
        return float(hi[0] - lo[0])

    @property
    def height(self) -> float:
        lo, hi = self.get_bbox()
        return float(hi[1] - lo[1])

    # -- transforms --------------------------------------------------------

    def shift(self, *vectors) -> "Shape":
        total = np.sum([np.asarray(v, dtype=float) for v in vectors], axis=0)
        return self.apply_points_function(lambda p: p + total)

    def move_to(self, target, aligned_edge=C.ORIGIN) -> "Shape":
        """Move so that ``aligned_edge`` of the bbox lands on ``target``."""
        point = target.get_corner(aligned_edge) if isinstance(target, Shape) else np.asarray(target, dtype=float)
        return self.shift(point - self.get_corner(aligned_edge))

    def scale(self, factor, about_point=None, about_edge=C.ORIGIN, scale_stroke: bool = False) -> "Shape":
        origin = self._about(about_point, about_edge)
        f = np.asarray(factor, dtype=float)
        self.apply_points_function(lambda p: origin + (p - origin) * f)
        if scale_stroke:
            s = float(np.mean(np.abs(f)))
            for m in self.family:
                if isinstance(m, VShape):
                    m.stroke_width *= s
        return self

    def stretch(self, factor: float, dim: int, about_point=None, about_edge=C.ORIGIN) -> "Shape":
        f = np.ones(2)
        f[dim] = factor
        return self.scale(f, about_point, about_edge)

    def rotate(self, angle: float, about_point=None, about_edge=C.ORIGIN) -> "Shape":
        origin = self._about(about_point, about_edge)
        c, s = np.cos(angle), np.sin(angle)
        R = np.array([[c, -s], [s, c]])
        return self.apply_points_function(lambda p: (p - origin) @ R.T + origin)

    def apply_matrix(self, matrix, about_point=None, about_edge=C.ORIGIN) -> "Shape":
        origin = self._about(about_point, about_edge)
        M = np.asarray(matrix, dtype=float)
        return self.apply_points_function(lambda p: (p - origin) @ M.T + origin)

    def apply_function(self, fn: Callable[[np.ndarray], np.ndarray], about_point=None) -> "Shape":
        """Apply an arbitrary point map (non-affine warps, coordinate changes)."""
        origin = np.zeros(2) if about_point is None else np.asarray(about_point, dtype=float)

        def wrapped(pts):
            return np.array([np.asarray(fn(p - origin), dtype=float) + origin for p in pts])

        return self.apply_points_function(wrapped)

    def flip(self, axis=C.UP, about_point=None, about_edge=C.ORIGIN) -> "Shape":
        """Mirror across the line through ``about_point`` spanned by ``axis``."""
        a = np.asarray(axis, dtype=float)
        norm = np.linalg.norm(a)
        if norm < 1e-12:
            return self
        a = a / norm
        M = 2 * np.outer(a, a) - np.eye(2)  # Householder reflection
        return self.apply_matrix(M, about_point, about_edge)

    def _about(self, about_point, about_edge) -> np.ndarray:
        if about_point is not None:
            return np.asarray(about_point, dtype=float)
        return self.get_corner(about_edge)

    # -- sizing ------------------------------------------------------------

    def set_width(self, width: float, stretch: bool = False, **kw) -> "Shape":
        return self._set_size(0, width, stretch, **kw)

    def set_height(self, height: float, stretch: bool = False, **kw) -> "Shape":
        return self._set_size(1, height, stretch, **kw)

    def _set_size(self, dim: int, value: float, stretch: bool, **kw) -> "Shape":
        current = (self.width, self.height)[dim]
        if current < 1e-9:
            return self
        factor = value / current
        return self.stretch(factor, dim, **kw) if stretch else self.scale(factor, **kw)

    def scale_to_fit(self, width: float | None = None, height: float | None = None) -> "Shape":
        """Scale uniformly to fit inside the given box."""
        f = []
        if width is not None and self.width > 1e-9:
            f.append(width / self.width)
        if height is not None and self.height > 1e-9:
            f.append(height / self.height)
        return self.scale(min(f)) if f else self

    # -- layout ------------------------------------------------------------

    def next_to(
        self,
        target,
        direction=C.RIGHT,
        buff: float = C.DEFAULT_BUFF,
        aligned_edge=C.ORIGIN,
    ) -> "Shape":
        """Place ``self`` beside ``target``, ``buff`` units away."""
        d = np.asarray(direction, dtype=float)
        anchor = target.get_corner(d + aligned_edge) if isinstance(target, Shape) else np.asarray(target, dtype=float)
        self.move_to(anchor, aligned_edge=-d + aligned_edge)
        return self.shift(d * buff)

    def align_to(self, target, direction=C.UP) -> "Shape":
        """Slide ``self`` so its ``direction`` edge matches ``target``'s."""
        d = np.asarray(direction, dtype=float)
        anchor = target.get_corner(d) if isinstance(target, Shape) else np.asarray(target, dtype=float)
        delta = np.where(d != 0, anchor - self.get_corner(d), 0.0)
        return self.shift(delta)

    def to_edge(self, direction=C.LEFT, buff: float = C.LARGE_BUFF) -> "Shape":
        d = np.asarray(direction, dtype=float)
        edge = d * np.array([C.FRAME_WIDTH / 2, C.FRAME_HEIGHT / 2])
        target = edge - d * buff
        delta = np.where(d != 0, target - self.get_corner(d), 0.0)
        return self.shift(delta)

    def to_corner(self, direction=C.UL, buff: float = C.LARGE_BUFF) -> "Shape":
        d = np.asarray(direction, dtype=float)
        for axis in (0, 1):
            if d[axis]:
                unit = np.zeros(2)
                unit[axis] = d[axis]
                self.to_edge(unit, buff)
        return self

    def center(self) -> "Shape":
        return self.shift(-self.get_center())

    def arrange(
        self,
        direction=C.RIGHT,
        buff: float = C.DEFAULT_BUFF,
        center: bool = True,
        aligned_edge=C.ORIGIN,
    ) -> "Shape":
        """Lay out submobjects in a row/column."""
        for prev, cur in itertools.pairwise(self.submobjects):
            cur.next_to(prev, direction, buff, aligned_edge)
        if center:
            self.center()
        return self

    def arrange_in_grid(
        self,
        rows: int | None = None,
        cols: int | None = None,
        buff=C.DEFAULT_BUFF,
        row_align=C.ORIGIN,
        col_align=C.ORIGIN,
        center: bool = True,
    ) -> "Shape":
        """Lay out submobjects on a grid, filling rows first."""
        n = len(self.submobjects)
        if n == 0:
            return self
        if rows is None and cols is None:
            cols = int(np.ceil(np.sqrt(n)))
        if cols is None:
            cols = int(np.ceil(n / rows))
        if rows is None:
            rows = int(np.ceil(n / cols))
        bx, by = (buff, buff) if np.isscalar(buff) else buff

        cell_w = max(m.width for m in self.submobjects) + bx
        cell_h = max(m.height for m in self.submobjects) + by
        for i, m in enumerate(self.submobjects):
            r, c = divmod(i, cols)
            cell = np.array([c * cell_w, -r * cell_h])
            m.move_to(cell + col_align * cell_w / 2 + row_align * cell_h / 2, aligned_edge=col_align + row_align)
        if center:
            self.center()
        return self

    # -- updaters ----------------------------------------------------------

    def add_updater(self, fn: Callable, call: bool = True) -> "Shape":
        """Register ``fn(mobject)`` or ``fn(mobject, dt)``, run every frame."""
        self.updaters.append(fn)
        if call:
            self.update(0.0)
        return self

    def remove_updater(self, fn: Callable) -> "Shape":
        while fn in self.updaters:
            self.updaters.remove(fn)
        return self

    def clear_updaters(self, recurse: bool = True) -> "Shape":
        self.updaters = []
        if recurse:
            for m in self.submobjects:
                m.clear_updaters()
        return self

    def update(self, dt: float = 0.0, recurse: bool = True) -> "Shape":
        for fn in self.updaters:
            if fn.__code__.co_argcount >= 2:
                fn(self, dt)
            else:
                fn(self)
        if recurse:
            for m in self.submobjects:
                m.update(dt)
        return self

    def has_updaters(self) -> bool:
        return any(m.updaters for m in self.family)

    # -- animation ---------------------------------------------------------

    @property
    def animate(self):
        """``self.play(mob.animate.shift(UP).set_color(RED))``"""
        from .animation.transform import AnimationBuilder

        return AnimationBuilder(self)

    def set_opacity(self, opacity: float) -> "Shape":
        """Scale how visible the whole family is, without losing its style."""
        for m in self.family:
            if isinstance(m, VShape):
                m.opacity_scale = float(opacity)
        return self

    def set_visible(self, visible: bool) -> "Shape":
        self._visible = visible
        return self

    def fix_in_frame(self, fixed: bool = True) -> "Shape":
        """Pin to the screen: the camera no longer moves or scales this."""
        for m in self.family:
            m.fixed_in_frame = fixed
        return self

    def interpolate_from(self, a: "Shape", b: "Shape", alpha: float) -> "Shape":
        """Blend between two states of the same object.

        The base class has no geometry of its own, so this is a no-op; it
        exists so ``Transform`` can walk a mixed family without type checks.
        """
        return self


# ==========================================================================
# VShape
# ==========================================================================


class VShape(Shape):
    """A mobject made of cubic-Bézier subpaths."""

    def __init__(
        self,
        *submobjects: Shape,
        fill_color=None,
        fill_opacity: float = 0.0,
        stroke_color=None,
        stroke_width: float = C.DEFAULT_STROKE_WIDTH,
        stroke_opacity: float = 1.0,
        color=None,
        opacity: float | None = None,
        cap: str = "round",
        join: str = "round",
        dash: Sequence[float] | None = None,
        fill_rule: str = "nonzero",
        **kwargs,
    ):
        super().__init__(*submobjects, **kwargs)
        self.subpaths: list[np.ndarray] = []
        self.closed: list[bool] = []
        self.glyph: GlyphRef | None = None
        self._geom_id = 0
        self._seg_cache = None

        base = to_color(color) if color is not None else None
        self.fill_color = to_color(fill_color) if fill_color is not None else (base or Color(_DEFAULT_COLOR))
        self.stroke_color = to_color(stroke_color) if stroke_color is not None else (base or Color(_DEFAULT_COLOR))
        self.fill_opacity = float(fill_opacity)
        self.stroke_opacity = float(stroke_opacity)
        self.stroke_width = float(stroke_width)
        self.cap = cap
        self.join = join
        self.dash = list(dash) if dash else None
        self.fill_rule = fill_rule
        self.gradient: "LinearGradient | None" = None
        #: Node-level multiplier applied to both paint opacities at render
        #: time.  Fades drive this instead of the intrinsic opacities, so an
        #: unfilled shape does not acquire a fill on the way in.
        self.opacity_scale = 1.0
        #: Fraction of the path (by arc length) that is drawn.  Progressive
        #: drawing animates *this* rather than rewriting the point array, so
        #: the browser can render it with stroke-dashoffset and the geometry
        #: stays a single static path.
        self.draw_range: tuple[float, float] = (0.0, 1.0)
        if opacity is not None:
            self.opacity_scale = float(opacity)

    # -- geometry ----------------------------------------------------------

    def has_points(self) -> bool:
        return any(len(sp) for sp in self.subpaths)

    def _own_points(self) -> np.ndarray:
        return np.concatenate(self.subpaths) if self.subpaths else np.zeros((0, 2))

    def _apply_own(self, fn) -> None:
        self.subpaths = [np.asarray(fn(sp), dtype=float) for sp in self.subpaths]
        self._touch()

    def _own_bbox(self):
        if not self.subpaths:
            return None
        los, his = [], []
        for sp in self.subpaths:
            if len(sp) == 0:
                continue
            lo, hi = _path_bbox(sp)
            los.append(lo)
            his.append(hi)
        if not los:
            return None
        return np.min(los, axis=0), np.max(his, axis=0)

    # -- construction ------------------------------------------------------

    def set_subpaths(self, subpaths: Iterable[np.ndarray], closed: Iterable[bool] | None = None) -> "VShape":
        self.subpaths = [np.asarray(sp, dtype=float).reshape(-1, 2) for sp in subpaths]
        if closed is None:
            self.closed = [False] * len(self.subpaths)
        else:
            self.closed = list(closed)
        while len(self.closed) < len(self.subpaths):
            self.closed.append(False)
        self._touch()
        return self

    def set_points_as_corners(self, points, close: bool = False) -> "VShape":
        """Straight-line path through ``points``."""
        pts = np.asarray(points, dtype=float).reshape(-1, 2)
        if close and len(pts) > 1 and not np.allclose(pts[0], pts[-1]):
            pts = np.vstack([pts, pts[0]])
        return self.set_subpaths([bz.line_handles(pts)], [close])

    def set_points_smoothly(self, points, close: bool = False) -> "VShape":
        """Smooth (centripetal Catmull-Rom) path through ``points``."""
        pts = np.asarray(points, dtype=float).reshape(-1, 2)
        return self.set_subpaths([bz.catmull_rom_handles(pts, closed=close)], [close])

    def append_subpath(self, points, closed: bool = False) -> "VShape":
        self.subpaths.append(np.asarray(points, dtype=float).reshape(-1, 2))
        self.closed.append(closed)
        self._touch()
        return self

    def n_curves(self) -> int:
        return sum(bz.curve_count(sp) for sp in self.subpaths)

    def point_from_proportion(self, alpha: float) -> np.ndarray:
        """Point at fraction ``alpha`` along the path, by arc length."""
        segs, lens = self._segments()
        if not segs:
            return np.zeros(2)
        total = lens.sum()
        if total < bz.EPS:
            return segs[0][0]
        target = np.clip(alpha, 0, 1) * total
        acc = np.cumsum(lens)
        i = int(np.searchsorted(acc, target))
        i = min(i, len(segs) - 1)
        prev = acc[i - 1] if i else 0.0
        t = (target - prev) / max(lens[i], bz.EPS)
        return bz.bezier(segs[i], float(np.clip(t, 0, 1)))

    def _segments(self):
        """Every cubic and its arc length, cached until the geometry changes.

        Progressive drawing and ``point_from_proportion`` both need this on
        every sampled frame; recomputing it for a few-thousand-segment curve
        each time is the difference between a 1 s and a 30 s build.
        """
        cached = self._seg_cache
        if cached is not None and cached[0] == self._geom_id:
            return cached[1], cached[2]
        segs, lens = [], []
        for sp in self.subpaths:
            n = bz.curve_count(sp)
            if n == 0:
                continue
            segs.extend(sp[3 * i : 3 * i + 4] for i in range(n))
            lens.append(bz.curve_lengths(sp))
        arr = np.concatenate(lens) if lens else np.zeros(0)
        self._seg_cache = (self._geom_id, segs, arr)
        return segs, arr

    def _touch(self) -> None:
        """Mark the geometry as changed, invalidating derived caches."""
        global _geom_counter
        _geom_counter += 1
        self._geom_id = _geom_counter

    def path_length(self) -> float:
        """Total arc length, in world units."""
        return float(self._segments()[1].sum())

    def set_draw_range(self, start: float = 0.0, end: float = 1.0) -> "VShape":
        self.draw_range = (float(start), float(end))
        return self

    def drawn_copy(self) -> "VShape":
        """A copy clipped to ``draw_range`` -- what a still frame shows."""
        a, b = self.draw_range
        if a <= 0.0 and b >= 1.0:
            return self
        clone = self.copy()
        clone.submobjects = []
        clone.become_partial(self, a, b)
        clone.draw_range = (0.0, 1.0)
        return clone

    def get_start(self) -> np.ndarray:
        return self.subpaths[0][0] if self.subpaths and len(self.subpaths[0]) else np.zeros(2)

    def get_end(self) -> np.ndarray:
        return self.subpaths[-1][-1] if self.subpaths and len(self.subpaths[-1]) else np.zeros(2)

    def reverse_direction(self) -> "VShape":
        self.subpaths = [sp[::-1].copy() for sp in self.subpaths]
        self._touch()
        return self

    # -- style -------------------------------------------------------------

    def set_fill(self, color=None, opacity: float | None = None, recurse: bool = True) -> "VShape":
        for m in self.family if recurse else [self]:
            if isinstance(m, VShape):
                if color is not None:
                    m.fill_color = to_color(color)
                if opacity is not None:
                    m.fill_opacity = float(opacity)
        return self

    def set_stroke(
        self,
        color=None,
        width: float | None = None,
        opacity: float | None = None,
        dash: Sequence[float] | None = None,
        recurse: bool = True,
    ) -> "VShape":
        for m in self.family if recurse else [self]:
            if isinstance(m, VShape):
                if color is not None:
                    m.stroke_color = to_color(color)
                if width is not None:
                    m.stroke_width = float(width)
                if opacity is not None:
                    m.stroke_opacity = float(opacity)
                if dash is not None:
                    m.dash = list(dash) or None
        return self

    def set_color(self, color, opacity: float | None = None, recurse: bool = True) -> "VShape":
        """Set stroke *and* fill colour, keeping existing opacities."""
        col = to_color(color)
        for m in self.family if recurse else [self]:
            if isinstance(m, VShape):
                m.fill_color = col
                m.stroke_color = col
                m.gradient = None
                if opacity is not None:
                    if m.fill_opacity:
                        m.fill_opacity = opacity
                    if m.stroke_opacity:
                        m.stroke_opacity = opacity
        return self

    def set_style(self, **kwargs) -> "VShape":
        fill = {k[5:]: v for k, v in kwargs.items() if k.startswith("fill_")}
        stroke = {k[7:]: v for k, v in kwargs.items() if k.startswith("stroke_")}
        if fill:
            self.set_fill(**fill)
        if stroke:
            self.set_stroke(**stroke)
        for k in ("cap", "join", "dash", "fill_rule"):
            if k in kwargs:
                for m in self.family:
                    if isinstance(m, VShape):
                        setattr(m, k, kwargs[k])
        return self

    def match_style(self, other: "VShape") -> "VShape":
        for m in self.family:
            if isinstance(m, VShape):
                m.fill_color = other.fill_color
                m.stroke_color = other.stroke_color
                m.fill_opacity = other.fill_opacity
                m.stroke_opacity = other.stroke_opacity
                m.stroke_width = other.stroke_width
                m.opacity_scale = other.opacity_scale
                m.gradient = other.gradient
        return self

    def fade(self, factor: float = 0.5) -> "VShape":
        for m in self.family:
            if isinstance(m, VShape):
                m.opacity_scale *= 1 - factor
        return self

    @property
    def effective_fill_opacity(self) -> float:
        return self.fill_opacity * self.opacity_scale

    @property
    def effective_stroke_opacity(self) -> float:
        return self.stroke_opacity * self.opacity_scale

    def set_gradient(self, *colors, angle: float = 0.0) -> "VShape":
        """Fill with a linear gradient at ``angle`` radians (0 = left→right).

        On a group (a ``Text``, say) the ramp spans the whole group: each leaf
        receives the slice of it that its own bounding box covers.  Giving
        every glyph the full ramp instead would make each letter individually
        rainbow, which is never what is wanted.
        """
        cols = [to_color(c) for c in colors]
        if len(cols) == 1:
            return self.set_fill(cols[0], opacity=1.0)

        leaves = [m for m in self.family if isinstance(m, VShape) and m.has_points()]
        if not leaves:
            return self
        if len(leaves) == 1:
            leaves[0].gradient = LinearGradient(cols, angle)
            leaves[0].fill_opacity = leaves[0].fill_opacity or 1.0
            return self

        direction = np.array([np.cos(angle), np.sin(angle)])
        lo, hi = self.get_bbox()
        corners = np.array([[lo[0], lo[1]], [hi[0], lo[1]], [lo[0], hi[1]], [hi[0], hi[1]]])
        proj = corners @ direction
        start, span = float(proj.min()), float(proj.max() - proj.min())
        if span < 1e-9:
            return self.set_fill(cols[0], opacity=1.0)

        for leaf in leaves:
            llo, lhi = leaf.get_bbox()
            lcorners = np.array([[llo[0], llo[1]], [lhi[0], llo[1]], [llo[0], lhi[1]], [lhi[0], lhi[1]]])
            lproj = lcorners @ direction
            t0 = (float(lproj.min()) - start) / span
            t1 = (float(lproj.max()) - start) / span
            leaf.gradient = LinearGradient(_ramp_slice(cols, t0, t1), angle)
            leaf.fill_opacity = leaf.fill_opacity or 1.0
        return self

    # -- morph support -----------------------------------------------------

    def align_points_with(self, other: "VShape") -> None:
        """Give ``self`` and ``other`` matching subpath/point structure."""
        _align_subpath_counts(self, other)
        for i in range(len(self.subpaths)):
            a, b = self.subpaths[i], other.subpaths[i]
            na, nb = bz.curve_count(a), bz.curve_count(b)
            n = max(na, nb, 1)
            if na < n:
                self.subpaths[i] = bz.insert_n_curves_to_points(a, n - na)
            if nb < n:
                other.subpaths[i] = bz.insert_n_curves_to_points(b, n - nb)
        # A morph looks wrong if one side is closed and the other is not; the
        # union is the safe choice (an open path drawn closed just gains a
        # zero-length join at the seam).
        self.closed = other.closed = [x or y for x, y in zip(self.closed, other.closed)]
        self._touch()
        other._touch()

    def become_partial(self, source: "VShape", a: float, b: float) -> "VShape":
        """Become the piece of ``source`` between arc-length fractions a and b."""
        segs, lens = source._segments()
        if not segs:
            self.subpaths, self.closed = [], []
            self._touch()
            return self
        total = lens.sum()
        if total < bz.EPS:
            self.subpaths = [sp.copy() for sp in source.subpaths]
            self.closed = list(source.closed)
            self._touch()
            return self

        lo, hi = np.clip(a, 0, 1) * total, np.clip(b, 0, 1) * total
        subpaths, closed = [], []
        walked = 0.0
        idx = 0
        for sp, is_closed in zip(source.subpaths, source.closed):
            n = bz.curve_count(sp)
            out: list[np.ndarray] = []
            for i in range(n):
                L = lens[idx + i]
                s0, s1 = walked, walked + L
                walked = s1
                if s1 <= lo or s0 >= hi or L < bz.EPS:
                    continue
                t0 = (lo - s0) / L if lo > s0 else 0.0
                t1 = (hi - s0) / L if hi < s1 else 1.0
                piece = bz.partial_cubic(segs[idx + i], t0, t1)
                out.append(piece if not out else piece[1:])
            idx += n
            if out:
                subpaths.append(np.concatenate([out[0]] + out[1:]) if len(out) > 1 else out[0])
                # Only a fully-drawn subpath keeps its close flag.
                closed.append(bool(is_closed and lo <= 0 and hi >= total))
        self.subpaths, self.closed = subpaths, closed
        self._touch()
        return self

    def interpolate_from(self, a: "VShape", b: "VShape", alpha: float, path_func=None) -> "VShape":
        """Set ``self`` to the blend of ``a`` and ``b`` (must be pre-aligned)."""
        if path_func is None:
            self.subpaths = [x + (y - x) * alpha for x, y in zip(a.subpaths, b.subpaths)]
        else:
            self.subpaths = [path_func(x, y, alpha) for x, y in zip(a.subpaths, b.subpaths)]
        self.closed = list(a.closed if alpha < 0.5 else b.closed)
        self._touch()
        from .color import interpolate_color

        self.fill_color = interpolate_color(a.fill_color, b.fill_color, alpha)
        self.stroke_color = interpolate_color(a.stroke_color, b.stroke_color, alpha)
        for attr in ("fill_opacity", "stroke_opacity", "stroke_width", "opacity_scale"):
            x, y = getattr(a, attr), getattr(b, attr)
            setattr(self, attr, x + (y - x) * alpha)
        self.draw_range = tuple(
            x + (y - x) * alpha for x, y in zip(a.draw_range, b.draw_range)
        )  # type: ignore[assignment]
        self.gradient = a.gradient if alpha < 0.5 else b.gradient
        # The blended outline is no longer the shared glyph, unless nothing moved.
        self.glyph = a.glyph if (alpha <= 0.0 and a.glyph) else (b.glyph if alpha >= 1.0 else None)
        return self


def _ramp_slice(colors: list[Color], t0: float, t1: float, steps: int = 5) -> list[Color]:
    """The part of a colour ramp between fractions ``t0`` and ``t1``."""
    from .color import color_gradient, interpolate_color

    def at(t: float) -> Color:
        t = float(np.clip(t, 0.0, 1.0)) * (len(colors) - 1)
        i = min(int(t), len(colors) - 2)
        return interpolate_color(colors[i], colors[i + 1], t - i)

    if t1 - t0 < 1e-9:
        return [at(t0), at(t0)]
    return [at(t0 + (t1 - t0) * k / (steps - 1)) for k in range(steps)]


class LinearGradient:
    __slots__ = ("colors", "angle")

    def __init__(self, colors: list[Color], angle: float = 0.0):
        self.colors = colors
        self.angle = angle

    def copy(self) -> "LinearGradient":
        return LinearGradient(list(self.colors), self.angle)

    def key(self) -> tuple:
        return (tuple(c.hexa() for c in self.colors), round(self.angle, 6))


# ==========================================================================
# groups
# ==========================================================================


class VGroup(VShape):
    """A container for shapes (:class:`VShape`). Indexing and iteration work."""

    def __init__(self, *mobjects, **kwargs):
        super().__init__(**kwargs)
        self.add(*_flatten(mobjects))

    def __add__(self, other) -> "VGroup":
        return VGroup(*self.submobjects, other)


class Group(Shape):
    """A container for arbitrary mobjects."""

    def __init__(self, *mobjects, **kwargs):
        super().__init__(**kwargs)
        self.add(*_flatten(mobjects))


class ValueTracker(Shape):
    """Holds a number that animations can drive; read it from updaters."""

    def __init__(self, value: float = 0.0, **kwargs):
        super().__init__(**kwargs)
        self._value = np.array([float(value), 0.0])

    def get_value(self) -> float:
        return float(self._value[0])

    def set_value(self, value: float) -> "ValueTracker":
        self._value[0] = float(value)
        return self

    def increment_value(self, d: float) -> "ValueTracker":
        self._value[0] += d
        return self

    # Participate in interpolation by exposing the value as a "point".
    def _own_points(self) -> np.ndarray:
        return self._value.reshape(1, 2)

    def _apply_own(self, fn) -> None:
        self._value = np.asarray(fn(self._value.reshape(1, 2)), dtype=float).reshape(2)

    def has_points(self) -> bool:
        return False

    def _own_bbox(self):
        return None

    def interpolate_from(self, a: "ValueTracker", b: "ValueTracker", alpha: float) -> "ValueTracker":
        self._value = a._value + (b._value - a._value) * alpha
        return self

    @property
    def animate(self):
        from .animation.transform import AnimationBuilder

        return AnimationBuilder(self)


# ==========================================================================
# helpers
# ==========================================================================


def _flatten(items) -> list[Shape]:
    out: list[Shape] = []
    for it in items:
        if isinstance(it, Shape):
            out.append(it)
        elif isinstance(it, (list, tuple, set)):
            out.extend(_flatten(it))
        elif it is None:
            continue
        else:
            raise TypeError(f"not a mobject: {it!r}")
    return out


def _match_length(target: list, source: list) -> None:
    """Grow/shrink ``target`` so it has as many entries as ``source``."""
    while len(target) < len(source):
        target.append(source[len(target)].copy())
    del target[len(source) :]


def _align_subpath_counts(a: VShape, b: VShape) -> None:
    """Pad whichever mobject has fewer subpaths with degenerate ones."""
    for src, dst in ((a, b), (b, a)):
        while len(dst.subpaths) < len(src.subpaths):
            # A point-sized subpath at the centre: new pieces grow out of the
            # middle of the shape rather than flying in from the origin.
            anchor = dst.get_center() if dst.has_points() else src.get_center()
            k = max(bz.curve_count(src.subpaths[len(dst.subpaths)]), 1)
            dst.subpaths.append(np.repeat(anchor[None, :], 3 * k + 1, axis=0))
            dst.closed.append(False)
    while len(a.closed) < len(a.subpaths):
        a.closed.append(False)
    while len(b.closed) < len(b.subpaths):
        b.closed.append(False)


def _path_bbox(points: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Exact bounding box of a ``3k+1`` cubic point array.

    Using the control polygon would be a strict over-estimate, which shows up
    as visibly wrong gaps in ``next_to``/``to_edge``.  So we solve
    ``p'(t) = 0`` per curve and per axis, and include the real roots in (0, 1).
    """
    pts = np.asarray(points, dtype=float)
    n = bz.curve_count(pts)
    if n == 0:
        return pts.min(axis=0), pts.max(axis=0)

    P0, P1, P2, P3 = (pts[k : 3 * n + k : 3] for k in (0, 1, 2, 3))

    lo = np.minimum(P0, P3).min(axis=0)
    hi = np.maximum(P0, P3).max(axis=0)

    # p'(t) / 3 = a t^2 + b t + c
    a = -P0 + 3 * P1 - 3 * P2 + P3
    b = 2 * (P0 - 2 * P1 + P2)
    c = P1 - P0

    quad = np.abs(a) > bz.EPS
    disc = np.where(quad, b * b - 4 * a * c, 0.0)
    sq = np.sqrt(np.maximum(disc, 0.0))
    with np.errstate(invalid="ignore", divide="ignore"):
        roots = [
            np.where(quad & (disc >= 0), (-b + sq) / (2 * np.where(quad, a, 1.0)), np.nan),
            np.where(quad & (disc >= 0), (-b - sq) / (2 * np.where(quad, a, 1.0)), np.nan),
            # Degenerate (a ~ 0): the derivative is linear.
            np.where(~quad & (np.abs(b) > bz.EPS), -c / np.where(np.abs(b) > bz.EPS, b, 1.0), np.nan),
        ]

    for t in roots:
        ok = np.isfinite(t) & (t > 0.0) & (t < 1.0)
        if not ok.any():
            continue
        ts = np.where(ok, t, 0.0)
        val = (1 - ts) ** 3 * P0 + 3 * (1 - ts) ** 2 * ts * P1 + 3 * (1 - ts) * ts**2 * P2 + ts**3 * P3
        lo = np.minimum(lo, np.where(ok, val, np.inf).min(axis=0))
        hi = np.maximum(hi, np.where(ok, val, -np.inf).max(axis=0))
    return lo, hi
