"""Assemble a slide as shared outlines (`<defs>`) placed with `<use>` matrices.

This is the *static* half of the similarity/dedup pass (Plan-SVG §4.3): each
distinct glyph outline is stored once in `<defs>`, keyed by a translation-
normalised hash of its em-space shape, and every occurrence becomes a `<use>`
with a matrix that carries font size and position. So repeated letters — and the
same glyph at different sizes — share one outline, because the em outline is
scale-independent (Pango/dvisvgm give us unhinted curves) and the size lives in
the matrix.

Visibility is a **gate** (:mod:`lemur.layout.steps`): a set of build-step
intervals. Every drawing call takes either the legacy ``appear``/``until`` pair
or a ``gate=``; the serialised element carries ``data-step``/``data-until`` (one
interval) or ``data-steps`` (several) for the runtime.

Paint order is emission order within three layers — panels/images at the back,
glyphs in the middle, overlays (arrows, frames, labels) on top — so a later
highlight is never hidden under an earlier panel.
"""

from __future__ import annotations

import hashlib

import numpy as np

from ..layout.steps import ALWAYS, combine, from_range, is_always
from ..typeset.geometry import fmt, path_d

__all__ = ["Slide", "Defs"]


def _key(canon: list[np.ndarray], places: int = 4) -> str:
    """Translation-normalised hash of a shape (already origin-subtracted)."""
    h = hashlib.blake2b(digest_size=12)
    for sp in canon:
        h.update(np.round(sp, places).tobytes())
        h.update(b"|")
    return h.hexdigest()


def _gate(appear, until, gate) -> tuple:
    if gate is not None:
        return tuple(gate)
    return from_range(appear or 0, until) if (appear or until is not None) else ALWAYS


def gate_attrs(gate) -> str:
    """The runtime attributes for a gate ('' when always visible)."""
    if is_always(gate):
        return ""
    if len(gate) == 1:
        a, u = gate[0]
        return f'data-step="{a}"' + (f' data-until="{u}"' if u is not None else "")
    first = gate[0][0] if gate else 0
    terms = ",".join(f"{a}-{'' if u is None else u}" for a, u in gate)
    return f'data-step="{first}" data-steps="{terms}"'


def visible_at(gate, step: int) -> bool:
    return any(a <= step and (u is None or step <= u) for a, u in gate)


class Defs:
    """A deck-wide outline store: every distinct outline once, shared by all
    slides (a `<use>` resolves across the inline `<svg>`s of one HTML page)."""

    def __init__(self, prefix: str = "g"):
        self.prefix = prefix
        self._ids: dict = {}
        self._order: list = []

    def id_for(self, key: str, d: str) -> str:
        i = self._ids.get(key)
        if i is None:
            i = f"{self.prefix}{len(self._order)}"
            self._ids[key] = i
            self._order.append((i, d))
        return i

    def __len__(self) -> int:
        return len(self._order)

    def to_svg(self) -> str:
        return "".join(f'<path id="{i}" d="{d}"/>' for i, d in self._order)


class Slide:
    """Collects placed pieces and serialises them to a deduplicated `<svg>`."""

    def __init__(self, width: int, height: int, bg: str):
        self.w, self.h, self.bg = width, height, bg
        self._defs: dict[str, str] = {}   # shape key -> canonical `d`
        self._order: list[str] = []       # defs order, for deterministic ids
        self._uses: list[tuple] = []      # (key, (a,b,c,d,e,f), fill, gate)
        self._rects: list[tuple] = []     # (svg, gate) panels/images behind glyphs
        self._overlays: list[tuple] = []  # (svg, gate) drawn on top (arrows, labels)
        self._marks: dict = {}            # name -> [x0,y0,x1,y1] union box (design px)
        self._mark_uses: dict = {}        # name -> [(key, matrix, gate, baseline)] its placements
        self._mark_gates: dict = {}       # name -> gate of its first placement
        self._mark_occ: dict = {}         # name -> [[x0,y0,x1,y1], …] one box per occurrence
        self._last_mark = None            # the mark of the previous placement
        self._mark_occ_gates: dict = {}   # name -> [gate, …] per occurrence
        self._mark_layer: dict = {}       # name -> indices (in _uses) of the glyphs showing last
        self.max_step = 0                 # the largest step any gate references
        self.warnings: list = []          # build diagnostics collected while drawing

    # -- marks (annotate / connect targets) ---------------------------------

    def mark_boxes(self, name: str) -> list:
        """One box per *occurrence* of the mark (a reused name is a group) —
        consecutive placements of the same mark form one occurrence."""
        return [tuple(b) for b in self._mark_occ.get(name, [])]

    def mark_union(self, name: str) -> "tuple | None":
        b = self._marks.get(name)
        return tuple(b) if b else None

    def mark_gate(self, name: str) -> tuple:
        """When the mark itself is visible (its first placement's gate)."""
        return self._mark_gates.get(name, ALWAYS)

    def colorize_mark(self, name: str, color: "str | None", appear: int = 0, gate=None,
                      emphasis=()) -> None:
        """Re-draw a mark's glyphs in ``color`` from build step ``appear`` on
        (``None`` keeps each glyph's own colour) — how `annotate` recolours or
        emphasises the part it points at. Each copy is also bound by its original's gate, so
        a recolour never shows a mark before (or after) the mark itself.

        ``emphasis`` (``bold``/``italic``/``underline``/``strike``) is applied to
        the copy without reflowing the line: bold as a hairline outline of the
        glyphs, italic as a slant, the rules as bars under/through the mark."""
        g = _gate(appear, None, gate)
        emphasis = set(emphasis or ())
        s0 = g[0][0] if g else 0
        # the copy *replaces* what is showing now (the original, or an earlier
        # recolour) from its step on: no glyph is ever drawn twice
        for idx in self._mark_layer.get(name, []):
            key, matrix, fill, ug, bold = self._uses[idx]
            keep = combine(ug, ((0, s0 - 1),)) if s0 > 0 else ()
            self._uses[idx] = (key, matrix, fill, keep, bold)
        layer = []
        for key, (a, b, c, d, e, f), og, base, fill0 in self._mark_uses.get(name, []):
            if "italic" in emphasis:
                # slant about the baseline: X += 0.2·(baseline − Y); the outline's
                # origin sits (base − f) above the baseline, so shift by that too
                c = c - 0.2 * d
                e = e + 0.2 * (base - f)
            layer.append(len(self._uses))
            self._add_use(key, (a, b, c, d, e, f), color or fill0, combine(og, g),
                          bold=("bold" in emphasis))
        self._mark_layer[name] = layer
        if emphasis & {"underline", "strike"}:
            for box, og in zip(self._mark_occ.get(name, []), self._mark_occ_gates.get(name, [])):
                x0, y0, x1, y1 = box
                h = y1 - y0
                gg = combine(og, g)
                if "underline" in emphasis:
                    self.add_overlay(f'<rect x="{fmt(x0)}" y="{fmt(y1 + h * 0.06)}" width="{fmt(x1 - x0)}" '
                                     f'height="{fmt(max(h * 0.05, 1.5))}" fill="{color}"/>', gate=gg)
                if "strike" in emphasis:
                    self.add_overlay(f'<rect x="{fmt(x0)}" y="{fmt(y0 + h * 0.5)}" width="{fmt(x1 - x0)}" '
                                     f'height="{fmt(max(h * 0.05, 1.5))}" fill="{color}"/>', gate=gg)

    # -- drawing -------------------------------------------------------------

    def _track(self, gate) -> None:
        for a, u in gate:
            self.max_step = max(self.max_step, a, u or 0)

    def add_overlay(self, svg: str, appear: int = 0, until: "int | None" = None, gate=None) -> None:
        """Arbitrary SVG drawn above the glyphs (arrows, annotation labels)."""
        g = _gate(appear, until, gate)
        self._track(g)
        self._overlays.append((svg, g))

    def add_back(self, svg: str, appear: int = 0, until: "int | None" = None, gate=None) -> None:
        """Arbitrary SVG drawn behind the glyphs (panels, images)."""
        g = _gate(appear, until, gate)
        self._track(g)
        self._rects.append((svg, g))

    def add_rect(self, x: float, y: float, w: float, h: float, fill: str, rx: float = 0.0,
                 appear: int = 0, until: "int | None" = None, opacity: "float | None" = None,
                 gate=None, stroke: "str | None" = None, stroke_width: float = 1.0) -> None:
        """A filled (optionally rounded, optionally stroked) panel drawn behind the
        glyphs — e.g. a code block's background or a per-step line highlight."""
        op = f' fill-opacity="{fmt(opacity)}"' if opacity is not None else ""
        st = (f' stroke="{stroke}" stroke-width="{fmt(stroke_width)}"' if stroke else "")
        svg = (
            f'<rect x="{fmt(x)}" y="{fmt(y)}" width="{fmt(w)}" height="{fmt(h)}" '
            f'rx="{fmt(rx)}" fill="{fill}"{op}{st}/>'
        )
        self.add_back(svg, appear, until, gate)

    def add_image(self, x: float, y: float, w: float, h: float, href: str,
                  appear: int = 0, until: "int | None" = None, gate=None) -> None:
        """A raster/embedded image (the one non-vector payload), placed and gated
        like a panel. ``href`` is a self-contained data URI (or, for a
        separate-images build, a relative path)."""
        svg = (
            f'<image x="{fmt(x)}" y="{fmt(y)}" width="{fmt(w)}" height="{fmt(h)}" '
            f'preserveAspectRatio="xMidYMid meet" href="{href}"/>'
        )
        self.add_back(svg, appear, until, gate)

    def _add_use(self, key, matrix, fill, gate, bold: bool = False) -> None:
        self._track(gate)
        self._uses.append((key, matrix, fill, gate, bold))

    def place(self, subpaths, closed, fs: float, x0: float, y0: float, fill: str,
              appear: int = 0, until: "int | None" = None, mark: "str | None" = None,
              gate=None) -> None:
        """Place one typeset piece given in em units (y-up, baseline 0).

        The block transform is ``X = x0 + ex*fs``, ``Y = y0 - ey*fs`` (the single
        y-flip from em-space into the design box). The piece is normalised to its
        own origin so identical shapes share one `<defs>` entry, and the origin
        is folded into the `<use>` matrix. ``appear``/``until`` (or ``gate``)
        gate it to build steps. If ``mark`` is given, the placement is recorded
        so annotate/connect can point at it and recolour it.
        """
        sps, cls = [], []
        for sp, c in zip(subpaths, closed):
            if len(sp):
                sps.append(np.asarray(sp, dtype=float))
                cls.append(c)
        if not sps:
            return
        g = _gate(appear, until, gate)
        origin = sps[0][0].copy()
        canon = [sp - origin for sp in sps]
        key = _key(canon)
        if key not in self._defs:
            self._defs[key] = path_d(canon, cls)
            self._order.append(key)
        e = x0 + fs * origin[0]
        f = y0 - fs * origin[1]
        matrix = (fs, 0.0, 0.0, -fs, e, f)
        self._add_use(key, matrix, fill, g)
        if mark:
            self._mark_uses.setdefault(mark, []).append((key, matrix, g, y0, fill))
            self._mark_layer.setdefault(mark, []).append(len(self._uses) - 1)
            self._mark_gates.setdefault(mark, g)
            occ = self._mark_occ.setdefault(mark, [])
            if self._last_mark != mark or not occ:          # a new occurrence starts
                occ.append(None)
                self._mark_occ_gates.setdefault(mark, []).append(g)
            for sp in sps:
                xs = x0 + sp[:, 0] * fs
                ys = y0 - sp[:, 1] * fs
                gb = (float(xs.min()), float(ys.min()), float(xs.max()), float(ys.max()))
                for boxes, i in ((self._marks, None), (occ, -1)):
                    b = boxes.get(mark) if i is None else boxes[i]
                    if b is None:
                        if i is None:
                            boxes[mark] = list(gb)
                        else:
                            boxes[i] = list(gb)
                    else:
                        b[0], b[1] = min(b[0], gb[0]), min(b[1], gb[1])
                        b[2], b[3] = max(b[2], gb[2]), max(b[3], gb[3])
        self._last_mark = mark

    def stats(self) -> tuple[int, int]:
        """``(placements, distinct_outlines)`` — the dedup ratio."""
        return len(self._uses), len(self._order)

    @staticmethod
    def _gate_open(inner: str, appear, until: "int | None" = None, final: "int | None" = None) -> str:
        """Wrap ``inner`` in a step-gated group, or return it bare if always on.
        ``appear`` may be a gate (a tuple of intervals) or a legacy step. With
        ``final`` (the slide's last step), a group that is hidden at the end is
        marked ``data-final="0"`` — print and the overview show the end state."""
        gate = appear if isinstance(appear, tuple) else _gate(appear, until, None)
        attrs = gate_attrs(gate)
        if not attrs:
            return inner
        if final is not None and not visible_at(gate, final):
            attrs += ' data-final="0"'
        return f'<g {attrs} opacity="0">{inner}</g>'

    def _runs(self, items) -> list:
        """Group consecutive items that share a gate, keeping paint order."""
        out: list = []
        for svg, gate in items:
            if out and out[-1][1] == gate:
                out[-1][0].append(svg)
            else:
                out.append(([svg], gate))
        return [Slide._gate_open("".join(s), g, final=self.max_step) for s, g in out]

    def to_svg(self, prefix: str = "", defs: "Defs | None" = None) -> str:
        """Serialise. With a deck-level ``defs``, outlines go into that shared
        store (dedup across slides) and this slide carries no `<defs>` of its
        own; otherwise ids are namespaced with ``prefix`` per slide."""
        if defs is not None:
            ids = {k: defs.id_for(k, self._defs[k]) for k in self._order}
            local = ""
        else:
            # ids are document-global once several slide SVGs share one HTML
            # page, so each slide namespaces its <defs> ids with a unique prefix.
            ids = {k: f"{prefix}g{i}" for i, k in enumerate(self._order)}
            local = "".join(f'<path id="{ids[k]}" d="{self._defs[k]}"/>' for k in self._order)

        glyphs = [
            (f'<use href="#{ids[key]}" '
             f'transform="matrix({fmt(a)},{fmt(b)},{fmt(c)},{fmt(d)},{fmt(e)},{fmt(f)})" '
             f'fill="{fill}"'
             + (f' stroke="{fill}" stroke-width="{fmt(0.035)}" stroke-linejoin="round"' if bold else "")
             + '/>', gate)
            for key, (a, b, c, d, e, f), fill, gate, bold in self._uses
        ]
        body = self._runs(self._rects) + self._runs(glyphs) + self._runs(self._overlays)

        bg = f'<rect x="0" y="0" width="{self.w}" height="{self.h}" fill="{self.bg}"/>'
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {self.w} {self.h}" '
            f'preserveAspectRatio="xMidYMid meet">{bg}<defs>{local}</defs>{"".join(body)}</svg>'
        )
