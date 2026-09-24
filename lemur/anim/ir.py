"""The intermediate representation: a slide deck as keyframe data.

The scene samples every animation at a series of alphas and hands the recorder
a state snapshot for each.  The recorder turns those snapshots into *tracks* --
sparse keyframes plus the name of a rate function -- which is all any backend
needs.  The browser runtime looks up and lerps; the PDF backend reads the last
keyframe.  Neither has to know what a "Transform" is, and neither can disagree
with the other about what an animation means.

Two passes do most of the work:

* :func:`rigid_transform` notices when a node's points are only ever an affine
  image of one reference shape, and emits a 6-number matrix track instead of
  full point arrays.  Text almost always qualifies, which keeps the output
  small and lets the browser composite it on the GPU.
* :func:`simplify` drops keyframes that linear interpolation already
  reproduces, so a straight move costs two keyframes while a rotation keeps as
  many as its curvature actually demands.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field, replace
from typing import Any, Iterable

import numpy as np

from .mobject import Shape, VShape
from ..typeset.geometry import path_d

__all__ = ["Recorder", "Segment", "NodeInfo", "build_slide", "simplify", "rigid_transform"]

# Tolerances.  A world unit is ~135 px at the default camera, so 2e-3 units is
# well under a third of a pixel.
POS_TOL = 2e-3
#: Point-list morphs ('d' tracks): a keyframe is dropped when linear
#: interpolation reproduces it within this (world units; 0.005 ≈ 0.7px on a
#: 1080p screen). 2-D shapes that change every frame are the bulk of an
#: animation's size, and sub-pixel motion error is invisible. (3-D shapes made
#: through a View ship world points instead — ``p3`` / ``a3`` at WORLD_TOL.)
MORPH_TOL = 5e-3
AFFINE_TOL = 1e-3
OPACITY_TOL = 3e-3
COLOR_TOL = 1.5 / 255
WIDTH_TOL = 0.02  # px
DRAW_TOL = 1e-3

#: Samples per second taken before simplification, by animation class.
#: "linear" animations are exactly reproduced by their endpoints.
SAMPLE_RATE = {"linear": 0.0, "normal": 24.0, "dense": 48.0}
MAX_SAMPLES = 240


# --------------------------------------------------------------------------
# recorded state
# --------------------------------------------------------------------------


@dataclass(slots=True)
class State:
    pts: np.ndarray | None
    struct: tuple
    fill: tuple
    fill_op: float
    stroke: tuple
    stroke_op: float
    width: float
    draw: tuple
    visible: bool
    p3: "np.ndarray | None" = None     # world poly: flat 3-D points
    a3: "np.ndarray | None" = None     # world anchor: the 3-D point the shape is pinned to
    g3: "np.ndarray | None" = None     # a ghost anchor (dim while hidden)


#: 3-D point tracks (world units): dropped keyframes may be off by this much.
WORLD_TOL = 3e-3


@dataclass
class NodeInfo:
    """Bookkeeping for one drawable mobject over the life of a slide."""

    index: int
    mobject: VShape
    z_index: float
    order: tuple
    glyph_key: str | None = None
    fixed: bool = False
    canonical: list[np.ndarray] | None = None
    canon_closed: list[bool] | None = None
    samples: list[State] = field(default_factory=list)
    gradient: Any = None
    _ref: Any = None

    def record(self, visible: bool) -> None:
        mob = self.mobject
        ref = tuple(id(sp) for sp in mob.subpaths)
        prev = self.samples[-1] if self.samples else None
        if prev is not None and ref == self._ref:
            pts, struct = prev.pts, prev.struct
        elif mob.subpaths:
            pts = np.concatenate(mob.subpaths)
            struct = (tuple(len(sp) for sp in mob.subpaths), tuple(bool(c) for c in mob.closed))
        else:
            pts, struct = None, ((), ())
        self._ref = ref

        p3 = a3 = g3 = None
        spec = getattr(mob, "world", None)
        if spec is not None:
            from . import world as W
            if spec.kind == "poly":
                polys = [np.asarray(P, dtype=float).reshape(-1, 3) for P in spec.points()]
                p3 = np.concatenate(polys) if polys else np.zeros((0, 3))
                struct = (tuple(len(P) for P in polys), tuple(bool(c) for c in spec.closed))
                pts = pts if pts is not None else np.zeros((1, 2))   # geometry lives in p3
                self._ref = None
            elif spec.kind in ("limb", "base"):
                pts = pts if pts is not None else np.zeros((1, 2))
                struct = ((), ())
                self._ref = None
            elif spec.kind == "anchor":
                a3 = np.asarray(spec.points(), dtype=float).reshape(3)
                if pts is not None:          # the outline relative to the projected anchor
                    pts = pts - W.project(W.camera_of(spec.view), a3)
                    self._ref = None
            if spec.ghost is not None:
                g3 = np.asarray(spec.ghost(), dtype=float).reshape(3)

        # ``view_alpha`` is a view-dependent dimming (e.g. a hidden-line ghost set
        # by a 3-D updater). Animations never touch it — they blend only the
        # opacities and ``opacity_scale`` — so a FadeIn and a per-frame
        # occlusion test can both act on the same shape without fighting.
        scale = mob.opacity_scale * getattr(mob, "view_alpha", 1.0)
        self.samples.append(
            State(
                pts=pts,
                struct=struct,
                fill=mob.fill_color.rgb,
                fill_op=float(mob.fill_opacity * scale * mob.fill_color.a),
                stroke=mob.stroke_color.rgb,
                stroke_op=float(mob.stroke_opacity * scale * mob.stroke_color.a),
                width=float(mob.stroke_width),
                draw=tuple(float(x) for x in mob.draw_range),
                visible=bool(visible and mob._visible and pts is not None),
                p3=p3, a3=a3, g3=g3,
            )
        )
        if mob.gradient is not None:
            self.gradient = mob.gradient

    def pad_to(self, n: int) -> None:
        """Nodes created part-way through a slide get invisible history."""
        if self.samples:
            return
        blank = State(None, ((), ()), (0, 0, 0), 0.0, (0, 0, 0), 0.0, 0.0, (0.0, 1.0), False)
        self.samples.extend([blank] * n)


@dataclass
class Segment:
    """One recorded stretch of time.

    A ``play()`` produces a window with uniformly spaced alphas; an instant
    change (``add``/``remove``) produces a single-sample segment at one instant.
    """

    t0: float
    t1: float
    rate: str
    alphas: list[float]
    start: int  # index of the first sample in every node's list


# --------------------------------------------------------------------------
# recorder
# --------------------------------------------------------------------------


class Recorder:
    """Collects samples for one slide."""

    def __init__(self):
        self.nodes: dict[int, NodeInfo] = {}
        self.segments: list[Segment] = []
        self.camera: list[tuple[float, float, float]] = []
        self._order = 0
        self._global: list = []               # every node id, in draw order
        self._global_pos: dict = {}
        self._n = 0  # samples taken so far
        self.views: list = []                 # Views whose world shapes the player projects
        self._view_ids: dict = {}
        self.view_cams: list = []             # per view: [(azim, elev)] per sample

    def view_index(self, view) -> int:
        """Register a View (first seen now); earlier samples get its current angles."""
        k = self._view_ids.get(id(view))
        if k is None:
            k = self._view_ids[id(view)] = len(self.views)
            self.views.append(view)
            cur = (float(view.azim.get_value()), float(view.elev.get_value()))
            self.view_cams.append([cur] * self._n)
        return k

    def _merge_order(self, seq: list) -> None:
        """Keep one global draw order across the whole recording. Draw order
        follows the scene graph, not the order things were animated in (a
        background added after its contents still goes behind) — but a shape
        keeps its place once it has one, so a label that is faded out early
        does not sink below everything that outlives it. A new shape goes right
        after the live shape before it in the scene graph."""
        glob = self._global
        pos = self._global_pos
        prev = None
        for k, key in enumerate(seq):
            if key not in pos:
                if prev is not None:
                    at = pos[prev] + 1
                else:                         # first in this sample: before the next known one
                    nxt = next((pos[s] for s in seq[k + 1:] if s in pos), len(glob))
                    at = nxt
                glob.insert(at, key)
                for i in range(at, len(glob)):
                    pos[glob[i]] = i
            prev = key
        for key, i in pos.items():
            self.nodes[key].order = (0, i)

    def _node_for(self, mob: VShape) -> NodeInfo:
        info = self.nodes.get(id(mob))
        if info is None:
            key = canon = closed = None
            if mob.glyph is not None:
                key, canon, closed = normalise_glyph(mob.glyph)
            info = NodeInfo(
                index=len(self.nodes),
                mobject=mob,
                z_index=mob.z_index,
                order=(self._n, self._order),
                glyph_key=key,
                fixed=bool(mob.fixed_in_frame),
                canonical=canon,
                canon_closed=closed,
            )
            self._order += 1
            self.nodes[id(mob)] = info
        info.pad_to(self._n)
        return info

    def sample(self, visible_roots: Iterable[Shape], camera_state) -> None:
        live: set[int] = set()
        seq: list = []
        for root in visible_roots:
            for m in root.family:
                if isinstance(m, VShape) and m.has_points():
                    live.add(id(m))
                    info = self._node_for(m)
                    info.z_index = m.z_index          # the latest z wins (bring_to_front later on)
                    seq.append(id(m))
        self._merge_order(seq)
        for key, info in self.nodes.items():
            spec = getattr(info.mobject, "world", None)
            if spec is not None:
                self.view_index(spec.view)
            info.record(key in live)
        for v, cams in zip(self.views, self.view_cams):
            cams.append((float(v.azim.get_value()), float(v.elev.get_value())))
        self.camera.append(camera_state)
        self._n += 1

    def open_segment(self, t0: float, t1: float, rate: str, alphas: list[float]) -> None:
        self.segments.append(Segment(t0, t1, rate, list(alphas), self._n))


def normalise_glyph(glyph) -> tuple[str, list[np.ndarray], list[bool]]:
    """Canonical (translation- and scale-free) form of a shared outline.

    Two 'e's in different words at different sizes normalise to the same
    points, so the deck stores one path and many transforms.
    """
    pts = np.concatenate(glyph.ref_subpaths)
    origin = pts.min(axis=0)
    span = float(np.linalg.norm(pts.max(axis=0) - origin))
    scale = 1.0 / span if span > 1e-9 else 1.0
    canon = [(sp - origin) * scale for sp in glyph.ref_subpaths]
    h = hashlib.blake2b(digest_size=10)
    for sp in canon:
        h.update(np.round(sp, 5).tobytes())
        h.update(b"|")
    return h.hexdigest(), canon, list(glyph.ref_closed)


# --------------------------------------------------------------------------
# analysis passes
# --------------------------------------------------------------------------


def simplify(alphas: list[float], values: list[np.ndarray], tol: float) -> list[int]:
    """Indices to keep so linear interpolation stays within ``tol``.

    Douglas-Peucker over the sample sequence.
    """
    n = len(values)
    if n <= 2:
        return list(range(n))
    keep = {0, n - 1}
    stack = [(0, n - 1)]
    while stack:
        lo, hi = stack.pop()
        if hi - lo < 2:
            continue
        a0, a1 = alphas[lo], alphas[hi]
        span = a1 - a0
        v0, v1 = values[lo], values[hi]
        worst, worst_i = tol, -1
        for i in range(lo + 1, hi):
            u = (alphas[i] - a0) / span if span > 1e-12 else 0.0
            err = float(np.max(np.abs(values[i] - (v0 + (v1 - v0) * u))))
            if err > worst:
                worst, worst_i = err, i
        if worst_i > 0:
            keep.add(worst_i)
            stack.append((lo, worst_i))
            stack.append((worst_i, hi))
    return sorted(keep)


def rigid_transform(source: np.ndarray, target: np.ndarray) -> np.ndarray | None:
    """Similarity map taking ``source`` onto ``target``, or ``None``.

    Deliberately restricted to rotation + uniform scale + translation (with or
    without a reflection) rather than a general affine.  Two reasons:

    * A general least-squares affine is under-determined when the source points
      are collinear -- a straight line, a tick mark -- and the minimum-norm
      solution it returns can be wildly anisotropic.  It maps the points
      correctly but squashes the *stroke* to nothing, because SVG strokes the
      path after transforming it.
    * Under a similarity the stroke stays circular, so dividing the stroke
      width by the scale reproduces exactly what the cairo backend draws.
      A non-uniform affine could not be matched that way.

    Anything that genuinely shears or stretches falls back to point keyframes.
    """
    if target is None or len(source) != len(target) or len(source) < 2:
        return None

    n = len(source)
    ones = np.ones(n)
    zeros = np.zeros(n)
    sx, sy = source[:, 0], source[:, 1]
    rhs = np.concatenate([target[:, 0], target[:, 1]])

    best = None
    for reflect in (False, True):
        # direct:    x' =  a*x - b*y + e,   y' = b*x + a*y + f
        # reflected: x' =  a*x + b*y + e,   y' = b*x - a*y + f
        s = -1.0 if reflect else 1.0
        top = np.stack([sx, -s * sy, ones, zeros], axis=1)
        bot = np.stack([s * sy, sx, zeros, ones], axis=1)
        A = np.vstack([top, bot])
        sol, *_ = np.linalg.lstsq(A, rhs, rcond=None)
        err = float(np.max(np.abs(A @ sol - rhs)))
        if best is None or err < best[0]:
            best = (err, sol, s)

    err, sol, s = best
    if err > AFFINE_TOL:
        return None
    a, b, e, f = sol
    if a * a + b * b < 1e-12:
        return None  # collapsed to a point; keep the geometry instead
    # SVG matrix(a b c d e f): x' = a*x + c*y + e, y' = b*x + d*y + f
    return np.array([a, b, -s * b, s * a, e, f])


# --------------------------------------------------------------------------
# IR construction
# --------------------------------------------------------------------------

_IDENTITY = np.array([1.0, 0.0, 0.0, 1.0, 0.0, 0.0])


class _TrackBuilder:
    """Accumulates tracks for one node, skipping anything already in effect."""

    def __init__(self, node_index: int):
        self.node = node_index
        self.tracks: list[dict] = []
        self.last: dict[str, np.ndarray] = {}

    def add(
        self,
        prop: str,
        seg: Segment,
        values: list[np.ndarray],
        tol: float,
        step: bool = False,
        extra: dict | None = None,
        places: int = 5,
    ) -> None:
        arr = [np.atleast_1d(np.asarray(v, dtype=float)) for v in values]
        if not arr:
            return
        prev = self.last.get(prop)
        constant = all(float(np.max(np.abs(v - arr[0]))) <= tol for v in arr)
        if constant and prev is not None and prev.shape == arr[0].shape and float(np.max(np.abs(arr[0] - prev))) <= tol:
            return  # already in effect; nothing to say
        self.last[prop] = arr[-1]

        if constant:
            keep = [0]
        elif step:
            # Only the instants where the value actually changes.
            keep = [0] + [i for i in range(1, len(arr)) if float(np.max(np.abs(arr[i] - arr[i - 1]))) > tol]
        else:
            keep = simplify(seg.alphas, arr, tol)

        track = {
            "n": self.node,
            "p": prop,
            "t0": round(seg.t0, 5),
            "t1": round(seg.t1, 5),
            "r": seg.rate,
            "a": [round(seg.alphas[i], 5) for i in keep],
            "v": [_round_list(arr[i], places) for i in keep],
        }
        if step:
            track["s"] = 1
        if extra:
            track.update(extra)
        self.tracks.append(track)


def _round_list(v: np.ndarray, places: int = 5) -> list[float]:
    return [round(float(x), places) for x in np.ravel(v)]


def build_slide(rec: Recorder, defs: dict[str, str], duration: float) -> dict:
    """Turn one slide's recording into nodes + tracks."""
    order = sorted(rec.nodes.values(), key=lambda n: (n.z_index, n.order))
    nodes_out: list[dict] = []
    tracks_out: list[dict] = []

    for slot, info in enumerate(order):
        info.index = slot

    for info in order:
        n_samples = len(info.samples)
        if n_samples == 0:
            continue
        spec = getattr(info.mobject, "world", None)
        if spec is not None and spec.kind != "anchor":
            node, tracks = _world_node(rec, info, spec)
            if node is not None:
                nodes_out.append(node)
                tracks_out.extend(tracks)
            continue

        # -- reference geometry ------------------------------------------
        # Use the *largest* sample, not the first.  A Grow animation starts
        # from a near-zero-size copy, and taking that as the reference would
        # leave every transform scaling by ~1e6 -- numerically hopeless, and
        # it drives the compensated stroke width below printable precision.
        first = _reference_sample(info.samples)
        if first is None:
            continue

        # Prefer the shared glyph outline (so many nodes collapse to one def),
        # but only if this node really is a rigid instance of it.
        options = []
        if info.canonical is not None:
            options.append(
                (
                    True,
                    np.concatenate(info.canonical),
                    (tuple(len(sp) for sp in info.canonical), tuple(info.canon_closed or [])),
                )
            )
        options.append((False, first.pts, first.struct))

        rigid = False
        for as_glyph, source, source_struct in options:
            mats, rigid = _fit_transforms(source, info.samples)
            if rigid:
                break
        if not rigid:
            as_glyph, source, source_struct = False, first.pts, first.struct
            mats = [None] * n_samples

        # -- node record --------------------------------------------------
        node: dict = {"i": info.index, "z": round(info.z_index, 4)}
        if info.fixed:
            node["fix"] = 1
        if rigid and as_glyph and info.glyph_key:
            node["k"] = "use"
            node["ref"] = info.glyph_key
            if info.glyph_key not in defs:
                defs[info.glyph_key] = path_d(info.canonical, info.canon_closed or [])
        else:
            node["k"] = "path"
            node["d"] = path_d(_unflatten(source, source_struct), source_struct[1])
            node["struct"] = [list(source_struct[0]), [int(c) for c in source_struct[1]]]
        node["len"] = round(_arc_length(source, source_struct), 4)
        if spec is not None:                     # an anchored shape: placed at a projected 3-D point
            node["w"] = rec.view_index(spec.view)
            node["wk"] = "anchor"
            if spec.rule:
                node["wr"] = spec.rule
            if spec.rule == "ghost" or spec.ghost is not None:
                node["ga"] = round(spec.ghost_alpha, 3)
        if info.mobject.dash:
            node["dash"] = [round(float(x), 4) for x in info.mobject.dash]
        if info.mobject.cap != "round":
            node["cap"] = info.mobject.cap
        if info.mobject.join != "round":
            node["join"] = info.mobject.join
        if info.mobject.fill_rule != "nonzero":
            node["rule"] = info.mobject.fill_rule
        if info.gradient is not None:
            node["grad"] = [c.hexa() for c in info.gradient.colors] + [round(info.gradient.angle, 4)]
        clip = getattr(info.mobject, "clip", None)
        if clip is not None:
            node["clip"] = [round(float(c), 3) for c in clip]   # (x, y, w, h) region to clip to

        tb = _TrackBuilder(info.index)
        for seg in rec.segments:
            lo, hi = seg.start, seg.start + len(seg.alphas)
            block = info.samples[lo:hi]
            if len(block) != len(seg.alphas):
                continue
            tb.add("v", seg, [[1.0 if s.visible else 0.0] for s in block], 0.5, step=True)
            if not any(s.visible for s in block):
                continue
            if rigid:
                tb.add("t", seg, [(m if m is not None else _IDENTITY) for m in mats[lo:hi]], POS_TOL)
            else:
                _add_path_track(tb, seg, block)
            tb.add("fc", seg, [s.fill for s in block], COLOR_TOL)
            tb.add("fo", seg, [[s.fill_op] for s in block], OPACITY_TOL)
            tb.add("sc", seg, [s.stroke for s in block], COLOR_TOL)
            tb.add("so", seg, [[s.stroke_op] for s in block], OPACITY_TOL)
            tb.add("sw", seg, [[s.width] for s in block], WIDTH_TOL)
            tb.add("dr", seg, [s.draw for s in block], DRAW_TOL)
            if spec is not None:
                tb.add("a3", seg, [s.a3 for s in block], WORLD_TOL, places=3)
                if spec.ghost is not None:
                    tb.add("g3", seg, [s.g3 for s in block], WORLD_TOL, places=3)

        _hoist_statics(node, tb)
        nodes_out.append(node)
        tracks_out.extend(tb.tracks)

    out = {"nodes": nodes_out, "tracks": tracks_out, "duration": round(duration, 4)}
    if rec.views:
        out["views"] = [_view_record(rec, k, v) for k, v in enumerate(rec.views)]
    return out


def _world_node(rec: "Recorder", info: NodeInfo, spec):
    """A 3-D shape the player projects: its world geometry (``p3``), its rule,
    and the usual style tracks — no 2-D geometry at all."""
    samples = info.samples
    node: dict = {"i": info.index, "z": round(info.z_index, 4), "k": "w",
                  "w": rec.view_index(spec.view), "wk": spec.kind}
    if spec.rule:
        node["wr"] = spec.rule
    if spec.normal is not None:
        node["nrm"] = [round(float(x), 4) for x in np.asarray(spec.normal, dtype=float)]
    if spec.ghost is not None:
        node["ga"] = round(spec.ghost_alpha, 3)
    first = next((s for s in samples if s.p3 is not None or spec.kind != "poly"), None)
    if first is None:
        return None, []
    if spec.kind == "poly":
        samples = _uniform_polys(samples)
        struct = next(s.struct for s in samples if s.p3 is not None)
        node["struct"] = [list(struct[0]), [int(c) for c in struct[1]]]
    mob = info.mobject
    if mob.dash:
        node["dash"] = [round(float(x), 4) for x in mob.dash]
    if mob.cap != "round":
        node["cap"] = mob.cap
    if mob.join != "round":
        node["join"] = mob.join
    if mob.fill_rule != "nonzero":
        node["rule"] = mob.fill_rule
    clip = getattr(mob, "clip", None)
    if clip is not None:
        node["clip"] = [round(float(c), 3) for c in clip]

    tb = _TrackBuilder(info.index)
    for seg in rec.segments:
        lo, hi = seg.start, seg.start + len(seg.alphas)
        block = samples[lo:hi]
        if len(block) != len(seg.alphas):
            continue
        tb.add("v", seg, [[1.0 if s.visible else 0.0] for s in block], 0.5, step=True)
        if not any(s.visible for s in block):
            continue
        if spec.kind == "poly":
            if any(s.p3 is None or s.struct != block[0].struct for s in block):
                continue                              # layout changed mid-segment: skip (rare)
            tb.add("p3", seg, [s.p3.ravel() for s in block], WORLD_TOL, places=3)
        if spec.ghost is not None:
            tb.add("g3", seg, [s.g3 for s in block], WORLD_TOL, places=3)
        tb.add("fc", seg, [s.fill for s in block], COLOR_TOL)
        tb.add("fo", seg, [[s.fill_op] for s in block], OPACITY_TOL)
        tb.add("sc", seg, [s.stroke for s in block], COLOR_TOL)
        tb.add("so", seg, [[s.stroke_op] for s in block], OPACITY_TOL)
        tb.add("sw", seg, [[s.width] for s in block], WIDTH_TOL)
        tb.add("dr", seg, [s.draw for s in block], DRAW_TOL)
    _hoist_statics(node, tb)
    return node, tb.tracks


def _uniform_polys(samples: list) -> list:
    """Give every sample of a world poly the same layout, so one ``struct`` fits
    all keyframes: shorter polylines repeat their last point (which draws
    nothing extra), missing ones collapse onto the previous one's end."""
    structs = {s.struct for s in samples if s.p3 is not None}
    if len(structs) <= 1:
        return samples
    n = max(len(st[0]) for st in structs)
    counts = [max((st[0][q] for st in structs if q < len(st[0])), default=1) for q in range(n)]
    closed = next(st[1] for st in structs if len(st[0]) == n)
    out = []
    for s in samples:
        if s.p3 is None:
            out.append(s)
            continue
        polys, off = [], 0
        for c in s.struct[0]:
            polys.append(s.p3[off:off + c])
            off += c
        fixed = []
        for q in range(n):
            P = polys[q] if q < len(polys) and len(polys[q]) else (fixed[-1][-1:] if fixed else np.zeros((1, 3)))
            fixed.append(np.concatenate([P, np.repeat(P[-1:], counts[q] - len(P), axis=0)]))
        out.append(replace(s, p3=np.concatenate(fixed), struct=(tuple(counts), tuple(closed))))
    return out


def _view_record(rec: "Recorder", k: int, view) -> dict:
    """A view's static projection and its camera angles over time."""
    occ = getattr(view, "occluder", None)
    out: dict = {"c": [round(float(view.center[0]), 5), round(float(view.center[1]), 5)],
                 "s": round(float(view.scale), 6),
                 "o": [round(float(x), 5) for x in view._data_origin],
                 "p": None if view._persp is None else float(view._persp),
                 "occ": None if not occ else {"c": [float(x) for x in occ["c"]], "R": float(occ["R"]),
                                              "cap": occ.get("cap")}}
    tb = _TrackBuilder(k)
    cams = rec.view_cams[k]
    for seg in rec.segments:
        lo, hi = seg.start, seg.start + len(seg.alphas)
        block = cams[lo:hi]
        if len(block) != len(seg.alphas):
            continue
        tb.add("ae", seg, [np.array(c) for c in block], 1e-5, places=6)
    tracks = tb.tracks
    if len(tracks) == 1 and len(tracks[0]["a"]) == 1:
        out["ae0"] = tracks[0]["v"][0]
    else:
        out["ae"] = tracks
        out["ae0"] = [round(c, 6) for c in cams[0]] if cams else [0.0, 0.0]
    return out


def _reference_sample(samples: list[State]) -> State | None:
    """The sample with the largest extent -- the best-conditioned reference."""
    best, best_span = None, -1.0
    seen: set[int] = set()
    for s in samples:
        if s.pts is None or id(s.pts) in seen:
            continue
        seen.add(id(s.pts))
        span = float(np.linalg.norm(s.pts.max(axis=0) - s.pts.min(axis=0)))
        if span > best_span:
            best, best_span = s, span
    return best


def _fit_transforms(source: np.ndarray, samples: list[State]) -> tuple[list, bool]:
    """Try to express every sample as a similarity image of ``source``."""
    mats: list[np.ndarray | None] = []
    miss = object()
    cache: dict[int, Any] = {}
    for s in samples:
        if s.pts is None:
            mats.append(None)
            continue
        m = cache.get(id(s.pts), miss)
        if m is miss:
            m = rigid_transform(source, s.pts)
            cache[id(s.pts)] = m
        mats.append(m)
        if m is None:
            return mats, False
    return mats, True


def _add_path_track(tb: _TrackBuilder, seg: Segment, block: list[State]) -> None:
    """Emit raw point keyframes for a genuinely deforming node."""
    usable = [s for s in block if s.pts is not None]
    if len(usable) != len(block):
        return  # geometry blinks in and out; visibility already covers it
    structs = {s.struct for s in usable}
    if len(structs) != 1:
        return  # point layout changed mid-animation: nothing sane to lerp
    struct = next(iter(structs))
    # A path made only of straight segments (a projected wireframe, a polyline)
    # is fully described by its anchors — the cubic controls sit at 1/3 and 2/3
    # of each segment. Store just those (a third ``struct`` entry flags it) and
    # the runtime draws `M…L…`: a third of the data for every 3-D orbit.
    if all(_is_polyline(s.pts, struct) for s in usable):
        tb.add(
            "d",
            seg,
            [_anchors(s.pts, struct).ravel() for s in usable],
            MORPH_TOL,
            extra={"struct": [[(n - 1) // 3 + 1 if n else 0 for n in struct[0]],
                              [int(c) for c in struct[1]], 1]},
            places=3,
        )
        return
    tb.add(
        "d",
        seg,
        [s.pts.ravel() for s in usable],
        MORPH_TOL,
        extra={"struct": [list(struct[0]), [int(c) for c in struct[1]]]},
        places=3,
    )


def _is_polyline(pts: np.ndarray, struct, tol: float = 1e-7) -> bool:
    """True when every cubic segment is a straight line with its controls at the
    thirds (what ``bezier.line_handles`` makes)."""
    k = 0
    for n in struct[0]:
        if n and (n - 1) % 3:
            return False
        for i in range(0, max(n - 1, 0), 3):
            a, c1, c2, b = pts[k + i], pts[k + i + 1], pts[k + i + 2], pts[k + i + 3]
            if (np.max(np.abs(c1 - (2 * a + b) / 3)) > tol or np.max(np.abs(c2 - (a + 2 * b) / 3)) > tol):
                return False
        k += n
    return True


def _anchors(pts: np.ndarray, struct) -> np.ndarray:
    out, k = [], 0
    for n in struct[0]:
        if n:
            out.append(pts[k:k + n:3])
        k += n
    return np.vstack(out) if out else pts[:0]


def _hoist_statics(node: dict, tb: _TrackBuilder) -> None:
    """Move single-keyframe tracks into the node's static attributes.

    A deck is mostly static: doing this here means the runtime does not have to
    evaluate a track per property per frame for things that never move.
    """
    keep: list[dict] = []
    static: dict[str, Any] = {}
    counts: dict[str, int] = {}
    for tr in tb.tracks:
        counts[tr["p"]] = counts.get(tr["p"], 0) + 1
    for tr in tb.tracks:
        if counts[tr["p"]] == 1 and len(tr["a"]) == 1:
            static[tr["p"]] = tr["v"][0]
        else:
            keep.append(tr)
    tb.tracks = keep
    if static:
        node["s"] = static


def _unflatten(pts: np.ndarray, struct) -> list[np.ndarray]:
    counts = struct[0]
    out, i = [], 0
    for c in counts:
        out.append(pts[i : i + c])
        i += c
    return out


def _arc_length(pts: np.ndarray, struct) -> float:
    """Total path length, needed for stroke-dash based progressive drawing."""
    from . import bezier as bz

    total = 0.0
    for sp in _unflatten(pts, struct):
        for i in range(bz.curve_count(sp)):
            total += bz.cubic_length(sp[3 * i : 3 * i + 4], samples=8)
    return total


def build_camera_tracks(rec: Recorder) -> list[dict]:
    tracks: list[dict] = []
    last: np.ndarray | None = None
    for seg in rec.segments:
        lo, hi = seg.start, seg.start + len(seg.alphas)
        block = [np.array(c, dtype=float) for c in rec.camera[lo:hi]]
        if len(block) != len(seg.alphas):
            continue
        constant = all(float(np.max(np.abs(c - block[0]))) <= POS_TOL for c in block)
        if constant and last is not None and float(np.max(np.abs(block[0] - last))) <= POS_TOL:
            continue
        last = block[-1]
        keep = [0] if constant else simplify(seg.alphas, block, POS_TOL)
        tracks.append(
            {
                "t0": round(seg.t0, 5),
                "t1": round(seg.t1, 5),
                "r": seg.rate,
                "a": [round(seg.alphas[i], 5) for i in keep],
                "v": [_round_list(block[i]) for i in keep],
            }
        )
    return tracks
