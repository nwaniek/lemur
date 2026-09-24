"""three — minimal 3D for build-time animations.

Real 3D, projected by the *player*: objects made through a :class:`View` carry
their 3-D geometry (a :class:`~lemur.anim.world.World` spec), and the deck
ships that geometry once plus a small camera track per view; the browser
projects every frame (``assets/svg/world.js``). So orbiting the camera costs a
few numbers per keyframe, not a re-projected copy of every shape. In Python the
shapes still re-project (an updater) so layout — ``next_to``, bounding boxes,
the still frame — sees the current 2-D picture.

    sp = View(elev=90)          # look straight down z: the xy-plane, head-on
    import numpy as np
    helix = sp.parametric(lambda t: (np.cos(t), np.sin(t), t / 3), 0, 6 * np.pi,
                          color="#2b6cb0", stroke_width=5)
    self.play(Create(helix)); self.next()
    self.play(*sp.reorient(elev=24, azim=-32), run_time=3)   # tilt into 3D

The view is a pair of animatable angles (:class:`ValueTracker`), so a camera
move is just ``self.play`` on them — one beat, like any other animation.
"""

from __future__ import annotations

from typing import Callable, Sequence

import numpy as np

from . import bezier as bz
from .mobject import ValueTracker, VGroup, VShape
from .world import World

__all__ = ["View", "Space3D"]


def _axspec(v):
    """A half-length ``v`` → ``(-v, v, None)``; a ``(lo, hi[, step])`` → itself."""
    if isinstance(v, (int, float)):
        return (-float(v), float(v), None)
    return (float(v[0]), float(v[1]), float(v[2]) if len(v) > 2 else None)


def _fmtnum(t: float) -> str:
    return str(int(round(t))) if abs(t - round(t)) < 1e-6 else f"{t:g}"


# Factory closures (1-arg updaters): a `lambda m, p=…` would be called as
# ``fn(self, dt)`` by add_updater (co_argcount >= 2), clobbering the binding.
def _tick_updater(view, p, perp, tick):
    def upd(m):
        c = view.project(p)
        m.set_subpaths([bz.line_handles(np.array([c - perp * tick, c + perp * tick]))], [False])
    return upd


def _num_updater(view, p, off):
    def upd(m):
        m.move_to(view.project(p) - off)
    return upd


class View:
    """One coordinate space seen through a camera — the unified plot surface for
    2D *and* 3D (a 2D plot is just the top-down case, ``elev=90``).

    ``elev`` is the camera's angle above the xy-plane in degrees (Blender-style
    z-up): ``90`` looks straight down z (x right, y up — a plain 2D plot); lowering
    it tilts so the camera stays *above* looking down and the z-axis stands upright.
    ``azim`` spins the scene about z. ``scale`` is animation units per world unit
    (or use :meth:`fit` to frame a data box into the ``viewport``). ``perspective``
    switches from parallel to a pinhole camera (nearer = bigger)."""

    def __init__(self, azim: float = 0.0, elev: float = 90.0, scale: float = 1.5,
                 viewport=None, perspective: "float | None" = None, static: bool = False):
        self.azim = ValueTracker(np.radians(azim))
        self.elev = ValueTracker(np.radians(elev))
        self.scale = float(scale)
        #: When True, shapes are projected once in Python (plain 2-D shapes, no
        #: world spec) — so the view can't orbit, but curves can be `Transform`ed
        #: into one another. Use it for a still plot (e.g. a 2D plot that morphs
        #: its graph).
        self._static = bool(static)
        #: Camera distance for a perspective view (nearer things look bigger).
        #: ``None`` = orthographic (parallel). Typical values are a few world radii.
        self._persp = None if perspective is None else float(perspective)
        #: A view = a camera (azim/elev/scale) + a **viewport**: the ``(cx, cy, w,
        #: h)`` rect on the slide it draws into. The projection is centred there and
        #: everything it makes is clipped to it — so the *same* plot code lands in
        #: the main area or an inset just by changing the viewport (matching a
        #: :func:`panel`). ``None`` = centred on the origin, unclipped.
        if viewport is None:
            self.center = np.array([0.0, 0.0])
            self._clip = None
            self._vp_wh = None
        else:
            cx, cy, w, h = viewport
            self.center = np.array([float(cx), float(cy)])
            self._clip = (cx - w / 2, cy - h / 2, float(w), float(h))
            self._vp_wh = (float(w), float(h))
        #: Data origin subtracted before projecting (set by :meth:`fit`, so a plot
        #: authored in data coordinates — even off-centre ones — lands centred).
        self._data_origin = np.zeros(3)
        #: A solid that hides what is behind it: a dict with the centre ``"c"``,
        #: the radius ``"R"`` and ``"cap"`` (``None`` for a sphere, or the height
        #: ``z`` of the ground a dome stands on). Used by the player's hidden-line
        #: and hide/ghost rules (see :mod:`lemur.anim.world`).
        self.occluder = None

    def _tag(self, mob):
        if self._clip is not None:
            for m in getattr(mob, "family", [mob]):
                m.clip = self._clip
        return mob

    # -- projection --------------------------------------------------------

    def project(self, p) -> np.ndarray:
        """A 3D point ``(x, y, z)`` → its 2D place on the animation plane. With a
        perspective camera, nearer points are magnified (divide by depth)."""
        x, y, z = np.asarray(p, dtype=float) - self._data_origin
        a, e = self.azim.get_value(), self.elev.get_value()
        ca, sa, se, ce = np.cos(a), np.sin(a), np.sin(e), np.cos(e)
        sx = ca * x - sa * y
        sy = (sa * x + ca * y) * se + z * ce
        if self._persp is not None:
            dc = z * se - (sa * x + ca * y) * ce           # depth toward the camera
            k = self._persp / max(self._persp - dc, 1e-3)  # >1 near, <1 far
            sx, sy = sx * k, sy * k
        return np.array([sx, sy]) * self.scale + self.center

    def depth(self, p) -> float:
        """Signed depth of a 3D point toward the camera (larger = nearer) — used to
        z-sort solid faces so nearer ones are drawn on top. With ``elev > 0`` the
        camera is *above* the xy-plane looking down, so larger z is nearer."""
        x, y, z = np.asarray(p, dtype=float) - self._data_origin
        a, e = self.azim.get_value(), self.elev.get_value()
        ca, sa, se, ce = np.cos(a), np.sin(a), np.sin(e), np.cos(e)
        return float(z * se - (sa * x + ca * y) * ce)

    def _bind(self, mob: VShape, points: Sequence, closed: bool) -> VShape:
        pts = [np.asarray(p, dtype=float) for p in points]
        arr = np.array(pts)

        def project_into(m):
            m.set_subpaths([bz.line_handles(np.array([self.project(p) for p in pts]))], [closed])

        if self._static:
            project_into(mob)                 # once — leaves the shape free to be Transformed
        else:
            mob.add_updater(project_into)     # re-project as the camera moves (for layout)
            # the player projects it: static 3-D points, however the camera moves
            mob.world = World(self, "poly", points=lambda: [arr], closed=[closed])
        return self._tag(mob)

    def curve_fn(self, points_fn: Callable[[], Sequence], closed: bool = False, rule=None,
                 ghost=None, ghost_alpha: float = 0.3, **style) -> VShape:
        """A 3-D polyline recomputed every frame from ``points_fn()`` (points that
        move, blend, unroll …). The player projects it; ``rule`` ``"vis"``/``"hid"``
        draws only the part not hidden / hidden by :attr:`occluder`; ``ghost`` (a
        3-D point callable) dims it while that point is hidden."""
        m = VShape(**style)

        def upd(mm):
            mm.set_subpaths([bz.line_handles(np.array([self.project(p) for p in points_fn()]))], [closed])

        m.add_updater(upd)
        m.world = World(self, "poly", points=lambda: [np.asarray(points_fn(), dtype=float)], closed=[closed],
                        rule=rule, ghost=ghost, ghost_alpha=ghost_alpha)
        return self._tag(m)

    def dot(self, where, radius: float = 0.08, color: str = "#c0392b", rule=None, **style):
        """A dot pinned to a 3-D point (or to ``where()``, if callable) — placed
        by the player. ``rule`` ``"hide"``/``"ghost"``: while the occluder hides it."""
        from .shapes import Circle

        at = where if callable(where) else (lambda w=np.asarray(where, dtype=float): w)
        style.setdefault("stroke_width", 0)
        d = Circle(radius=radius, fill_color=color, fill_opacity=1.0, **style)
        d.add_updater(lambda m: m.move_to(self.project(at())))
        return self.pin(d, at, rule=rule)

    def pin(self, mob, where, rule=None, offset=(0.0, 0.0), ghost_alpha: float = 0.3):
        """Pin a 2-D shape or group (a dot, a label) to a 3-D point: the player
        places it at the projected point (+ ``offset``, in animation units)."""
        at = where if callable(where) else (lambda w=np.asarray(where, dtype=float): w)
        off = np.asarray(offset, dtype=float)
        if not any(getattr(u, "_lmr_pin", False) for u in getattr(mob, "updaters", [])):
            def upd(m):
                m.move_to(self.project(at()) + off)
            upd._lmr_pin = True
            mob.add_updater(upd)
        for m in getattr(mob, "family", [mob]):
            m.world = World(self, "anchor", points=at, rule=rule, ghost_alpha=ghost_alpha)
        return self._tag(mob)

    # -- primitives (all re-project as the view moves) ---------------------

    def curve(self, points: Sequence, closed: bool = False, **style) -> VShape:
        """A polyline through 3D ``points`` (a smooth-looking curve if dense)."""
        return self._bind(VShape(**style), points, closed)

    def parametric(self, fn: Callable[[float], Sequence], t0: float, t1: float,
                   samples: int = 200, closed: bool = False, **style) -> VShape:
        """The 3D curve ``fn(t)`` for ``t`` in ``[t0, t1]``."""
        return self.curve([fn(t) for t in np.linspace(t0, t1, samples)], closed, **style)

    def line(self, a: Sequence, b: Sequence, **style) -> VShape:
        """A 3D segment from ``a`` to ``b`` (e.g. an axis)."""
        return self.curve([a, b], **style)

    # -- data-space plotting (a 2D plot is just the top-down view, elev=90) ---

    def fit(self, x, y, z=(0.0, 0.0), margin: float = 0.88) -> "View":
        """Frame a data box (``x=(x0,x1)``, ``y=(y0,y1)``, ``z=(z0,z1)``) into the
        viewport: centre it and pick the scale so it fills the rect at the current
        angle. Afterwards :meth:`point`/:meth:`plot`/:meth:`axes` work in *data*
        coordinates. This is what makes a 2D plot (``elev=90``) or a 3D one place
        the same way — author the plot, then fit it to wherever it should land."""
        (x0, x1), (y0, y1), (z0, z1) = x, y, z
        self._data_origin = np.array([(x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2])
        self.scale = 1.0
        c = np.array([self.project((cx, cy, cz)) - self.center
                      for cx in (x0, x1) for cy in (y0, y1) for cz in (z0, z1)])
        bw = max(c[:, 0].max() - c[:, 0].min(), 1e-6)
        bh = max(c[:, 1].max() - c[:, 1].min(), 1e-6)
        w, h = self._vp_wh or (bw / margin, bh / margin)
        self.scale = margin * min(w / bw, h / bh)
        return self

    def point(self, x: float, y: float, z: float = 0.0) -> np.ndarray:
        """A data point ``(x, y[, z])`` → its place on the slide (like matplotlib's
        ``transData`` / an Axes' ``coords_to_point``)."""
        return self.project((x, y, z))

    def plot(self, fn: Callable[[float], float], x0: float, x1: float,
             samples: int = 200, **style) -> VShape:
        """The graph ``y = fn(x)`` over ``[x0, x1]`` (on the z=0 plane). Anything
        outside the viewport is simply clipped — no y-range juggling."""
        xs = np.linspace(x0, x1, samples)
        return self.curve([(t, fn(t), 0.0) for t in xs], **style)

    def area(self, fn: Callable[[float], float], x0: float, x1: float, base: float = 0.0,
             samples: int = 120, **style) -> VShape:
        """The filled region between ``fn`` and ``y = base`` over ``[x0, x1]``."""
        style.setdefault("fill_opacity", 0.28)
        style.setdefault("stroke_width", 0.0)
        xs = np.linspace(x0, x1, samples)
        pts = [(x0, base, 0.0)] + [(t, fn(t), 0.0) for t in xs] + [(x1, base, 0.0)]
        return self.polygon(pts, **style)

    def axes(self, x=3.0, y=3.0, z=3.0, numbers: bool = False, tick: float = 0.09,
             font_size: float = 20, num_color: str = "#5f6368", num_buff: float = 0.05,
             **style) -> VGroup:
        """The three coordinate axes. Each of ``x``/``y``/``z`` is a half-length
        (``±v``) or a ``(lo, hi, step)`` range; with ``step`` (or ``numbers=True``)
        the axis gets tick marks and — when ``numbers`` — numeric labels, drawn on
        the far side of the axis in the projected view (good for the near-flat
        inset views). All of it re-projects and clips with the rest of the view."""
        from .text import Text

        style.setdefault("color", "#9aa0a6")
        style.setdefault("stroke_width", 1.6)
        g = VGroup()
        units = (np.array([1.0, 0, 0]), np.array([0, 1.0, 0]), np.array([0, 0, 1.0]))
        for u, spec in zip(units, (_axspec(x), _axspec(y), _axspec(z))):
            lo, hi, step = spec
            if abs(hi - lo) < 1e-9:           # a degenerate axis (e.g. z on a 2D plot)
                continue
            g.add(self.line(u * lo, u * hi, **style))
            if not step:
                continue
            pa, pb = self.project(u * lo), self.project(u * hi)     # projected axis dir (static view)
            d = pb - pa
            n = float(np.hypot(*d)) or 1.0
            perp = np.array([-d[1] / n, d[0] / n])                  # perpendicular, in slide units
            # put numbers below a horizontal-ish axis, left of a vertical-ish one
            if abs(d[0]) >= abs(d[1]):
                sgn = 1.0 if perp[1] < 0 else -1.0
            else:
                sgn = 1.0 if perp[0] < 0 else -1.0
            ndir = perp * sgn                                       # unit offset direction
            for t in np.arange(lo, hi + step * 0.5, step):
                if abs(t) < step * 0.25:                            # skip the origin
                    continue
                p3 = u * t
                mark = VShape(color=style["color"], stroke_width=style["stroke_width"])
                mark.add_updater(_tick_updater(self, p3, perp, tick))
                g.add(self._tag(mark))
                if numbers:
                    lab = Text(_fmtnum(t), font_size=font_size, color=num_color)
                    # nudge the number just clear of the tick: past its own half-extent
                    # along the offset direction, plus a small buffer
                    ext = lab.height / 2 if abs(ndir[1]) >= abs(ndir[0]) else lab.width / 2
                    lab.add_updater(_num_updater(self, p3, ndir * (tick + ext + num_buff)))
                    g.add(self._tag(lab))
        return g

    def label(self, text: str, anchor: Sequence, **style):
        """Upright text pinned to a 3D ``anchor`` (it tracks the anchor's screen
        position as the view moves, but never rotates)."""
        from .text import Text

        t = Text(text, **style)
        pt = np.asarray(anchor, dtype=float)
        if self._static:
            t.add_updater(lambda m: m.move_to(self.project(pt)))
            return self._tag(t)
        return self.pin(t, pt)

    def surface(self, fn: Callable[[float, float], Sequence], u_range, v_range,
                u_lines: int = 13, v_lines: int = 13, samples: int = 28, **style):
        """A **wireframe** surface ``fn(u, v) → (x, y, z)`` as a grid of u- and
        v-lines (each re-projects on orbit — keep the grid modest so orbiting stays
        cheap). Returns a :class:`VGroup`."""
        style.setdefault("color", "#2b6cb0")
        style.setdefault("stroke_width", 1.1)
        g = VGroup()
        for u in np.linspace(u_range[0], u_range[1], u_lines):
            g.add(self.parametric(lambda v, u=u: fn(u, v), v_range[0], v_range[1], samples, **style))
        for v in np.linspace(v_range[0], v_range[1], v_lines):
            g.add(self.parametric(lambda u, v=v: fn(u, v), u_range[0], u_range[1], samples, **style))
        return g

    def toward_camera(self) -> np.ndarray:
        """The unit vector from the scene toward the camera (for the current angles):
        a surface normal ``n`` faces the viewer when ``n @ view.toward_camera() > 0``."""
        a, e = self.azim.get_value(), self.elev.get_value()
        return np.array([-np.sin(a) * np.cos(e), -np.cos(a) * np.cos(e), np.sin(e)])

    def shaded_surface(self, fn: Callable[[float, float], Sequence], u_range, v_range,
                       nu: int = 24, nv: int = 12, light=(-0.4, -0.6, 0.9),
                       colors=("#5b7896", "#eef4fa"), ambient: float = 0.28,
                       bands: "int | None" = None, band_mix: float = 0.55,
                       mesh: "float | None" = 0.12, mesh_width: float = 0.7,
                       cull: bool = True, flip: bool = False, fill_light=None) -> VGroup:
        """An **opaque, lit** surface ``fn(u, v) → (x, y, z)``, as a mesh of
        ``nu × nv`` filled quads — the illustrated look of a paper figure rather
        than a wireframe.

        Each face is coloured once by a Lambert term against a fixed world-space
        ``light``: ``colors`` runs from shadow to lit, ``ambient`` lifts the
        shadow, and ``bands`` (e.g. 6) softly quantises the ramp into cel-style
        steps (``band_mix`` blends the stepped and the smooth ramp). ``mesh``
        darkens each face's outline by that amount, so the quads read as a fine
        mesh (``None`` = seamless, outlines in the face colour). With ``cull``,
        faces turned away from the camera are hidden every frame — for a
        **convex** surface that alone gets the occlusion right while the camera
        orbits (no depth sort needed). ``flip`` reverses the outward normal.
        ``fill_light=(direction, colour, strength)`` adds a second, tinted light
        (a warm fill from the side opposite the key light, say).

        Culling hides whole faces, so along the silhouette the mesh ends in a
        fine staircase; put a coarse, *unculled* copy underneath (``cull=False``,
        ``mesh=None``) to fill those slivers with the right tones."""
        from .color import interpolate_color, darken

        L = np.asarray(light, dtype=float)
        L = L / (np.linalg.norm(L) or 1.0)
        us = np.linspace(u_range[0], u_range[1], nu + 1)
        vs = np.linspace(v_range[0], v_range[1], nv + 1)
        grid = [[np.asarray(fn(u, v), dtype=float) for v in vs] for u in us]
        g = VGroup()
        for i in range(nu):
            for j in range(nv):
                quad = [grid[i][j], grid[i + 1][j], grid[i + 1][j + 1], grid[i][j + 1]]
                n = np.cross(quad[2] - quad[0], quad[3] - quad[1])
                if np.linalg.norm(n) < 1e-12:                      # a degenerate (pole) face
                    n = np.cross(quad[1] - quad[0], quad[3] - quad[0])
                n = n / (np.linalg.norm(n) or 1.0) * (-1.0 if flip else 1.0)
                lam = ambient + (1.0 - ambient) * max(0.0, float(n @ L))
                if bands:
                    lam = band_mix * (np.round(lam * bands) / bands) + (1.0 - band_mix) * lam
                col = interpolate_color(colors[0], colors[1], float(np.clip(lam, 0.0, 1.0)))
                if fill_light is not None:
                    fd, fcol, fk = fill_light
                    fd = np.asarray(fd, dtype=float) / (np.linalg.norm(fd) or 1.0)
                    col = interpolate_color(col, fcol, float(np.clip(fk * max(0.0, float(n @ fd)), 0.0, 1.0)))
                edge = darken(col, mesh) if mesh else col
                face = VShape(fill_color=col, fill_opacity=1.0, stroke_color=edge,
                              stroke_width=mesh_width)
                g.add(self._face(face, quad, n, cull))
        return g

    def _face(self, m: VShape, pts, normal, cull: bool) -> VShape:
        pts = [np.asarray(p, dtype=float) for p in pts]
        arr = np.array(pts)

        def upd(mm):
            mm.set_subpaths([bz.line_handles(np.array([self.project(p) for p in pts]))], [True])

        m.add_updater(upd)
        # the player projects the face and culls it when it turns away
        m.world = World(self, "poly", points=lambda: [arr], closed=[True],
                        rule="cull" if cull else None, normal=np.asarray(normal, dtype=float))
        return self._tag(m)

    def polygon(self, points: Sequence, **style) -> VShape:
        """A filled 3-D polygon (a flat face), re-projecting with the view."""
        style.setdefault("fill_opacity", 1.0)
        style.setdefault("stroke_width", 0.6)
        pts = [np.asarray(p, dtype=float) for p in points]
        arr = np.array(pts)
        m = VShape(**style)
        m.add_updater(lambda mm: mm.set_subpaths(
            [bz.line_handles(np.array([self.project(p) for p in pts]))], [True]))
        m.world = World(self, "poly", points=lambda: [arr], closed=[True])
        return self._tag(m)

    def solid(self, vertices: Sequence, faces: Sequence, sort: bool = True, **style) -> VGroup:
        """A solid from ``vertices`` (3-D points) and ``faces`` (each a list of
        vertex indices). Faces are painter-sorted by depth so nearer ones cover
        farther ones — **correct for a still view** (the order is baked, so it will
        not update if the camera orbits; rotate wireframes, not solids)."""
        verts = [np.asarray(v, dtype=float) for v in vertices]
        g = VGroup()
        for f in faces:
            pts = [verts[i] for i in f]
            m = self.polygon(pts, **style)
            if sort:
                # z_index = depth toward camera: the emitter draws low→high, so far
                # (small/negative depth) is drawn first and near ends up on top. Using
                # the depth itself (not a rank) lets faces of *several* solids compose.
                m.set_z_index(self.depth(np.mean(pts, axis=0)))
            g.add(m)
        return g

    def box(self, center=(0.0, 0.0, 0.0), size=1.0, **style) -> VGroup:
        """A z-sorted solid box centred at ``center`` (a scalar or ``(sx,sy,sz)``
        size). Handy building block for 3-D bars / block scenes in perspective."""
        c = np.asarray(center, dtype=float)
        h = (np.array([size, size, size], dtype=float) if np.isscalar(size)
             else np.asarray(size, dtype=float)) / 2.0
        V = np.array([[sx, sy, sz] for sz in (-1, 1) for sy in (-1, 1) for sx in (-1, 1)],
                     dtype=float) * h + c

        def vi(sx, sy, sz):
            return ((sz + 1) // 2) * 4 + ((sy + 1) // 2) * 2 + ((sx + 1) // 2)

        faces = [[vi(-1, -1, -1), vi(1, -1, -1), vi(1, 1, -1), vi(-1, 1, -1)],
                 [vi(-1, -1, 1), vi(1, -1, 1), vi(1, 1, 1), vi(-1, 1, 1)],
                 [vi(-1, -1, -1), vi(1, -1, -1), vi(1, -1, 1), vi(-1, -1, 1)],
                 [vi(-1, 1, -1), vi(1, 1, -1), vi(1, 1, 1), vi(-1, 1, 1)],
                 [vi(-1, -1, -1), vi(-1, 1, -1), vi(-1, 1, 1), vi(-1, -1, 1)],
                 [vi(1, -1, -1), vi(1, 1, -1), vi(1, 1, 1), vi(1, -1, 1)]]
        return self.solid(V, faces, **style)

    def trace_dot(self, points: Sequence, progress, radius: float = 0.09,
                  color: str = "#c0392b", by: str = "arc"):
        """A dot that rides a 3D polyline at fractional position ``progress`` (a
        :class:`ValueTracker` or a 0..1 callable). ``by="arc"`` (default) moves at
        constant speed (3D arc length) — good for sweeping a *finished* curve;
        ``by="index"`` moves by point index — pair it with :meth:`rate` so the dot
        sits exactly on a growing curve's drawn head, in step across several views.
        Share one ``progress`` to move the same point in every view at once."""
        from .shapes import Circle

        pts = np.asarray(points, dtype=float)
        n = len(pts)
        get = progress.get_value if hasattr(progress, "get_value") else progress
        if by == "index":
            def at3() -> np.ndarray:
                i = float(np.clip(get(), 0.0, 1.0)) * (n - 1)
                lo = min(int(np.floor(i)), n - 2)
                return pts[lo] * (1 - (i - lo)) + pts[lo + 1] * (i - lo)
        else:
            seg = np.linalg.norm(np.diff(pts, axis=0), axis=1)
            s = np.concatenate([[0.0], np.cumsum(seg)])
            total = s[-1] or 1.0

            def at3() -> np.ndarray:
                d = float(np.clip(get(), 0.0, 1.0)) * total
                i = int(np.clip(np.searchsorted(s, d, side="right") - 1, 0, n - 2))
                span = s[i + 1] - s[i]
                a = (d - s[i]) / span if span > 1e-12 else 0.0
                return pts[i] * (1 - a) + pts[i + 1] * a

        dot = Circle(radius=radius, fill_color=color, fill_opacity=1.0, stroke_width=0)
        dot.add_updater(lambda m: m.move_to(self.project(at3())))
        return self.pin(dot, at3) if not self._static else self._tag(dot)

    def rate(self, points: Sequence):
        """A `Create` ``rate_func`` that draws this view's projected polyline at
        uniform speed along the *original* point order — so its drawn tip tracks a
        `trace_dot(..., by="index")` on the same ``progress``, and several views
        drawing the same data stay in lock-step (each foreshortens differently, so
        each needs its own rate). Assumes the camera is still while drawing."""
        proj = np.array([self.project(p) for p in np.asarray(points, dtype=float)])
        seg = np.linalg.norm(np.diff(proj, axis=0), axis=1)
        s = np.concatenate([[0.0], np.cumsum(seg)])
        total = s[-1] or 1.0
        n = len(proj)

        def r(a: float) -> float:
            i = float(np.clip(a, 0.0, 1.0)) * (n - 1)
            lo = min(int(np.floor(i)), n - 2)
            return float(s[lo] * (1 - (i - lo)) + s[lo + 1] * (i - lo)) / total

        return r

    # -- moving the camera -------------------------------------------------

    def reorient(self, azim: float | None = None, elev: float | None = None) -> list:
        """Animations that move the camera to ``azim``/``elev`` (degrees). Splat
        into ``self.play`` — ``self.play(*sp.reorient(elev=24, azim=-32))``."""
        anims = []
        if elev is not None:
            anims.append(self.elev.animate.set_value(np.radians(elev)))
        if azim is not None:
            anims.append(self.azim.animate.set_value(np.radians(azim)))
        return anims


Space3D = View   # back-compat alias for the former name
