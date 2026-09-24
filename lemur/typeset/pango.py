"""Pango/HarfBuzz text -> vector outlines.

Pango does the hard part (itemisation, shaping, kerning, ligatures, bidi, line
breaking). We take the resulting outline path and split it back into clusters,
so each visible character can later be coloured, revealed or animated on its
own. Mined from wanim (plans/Plan-SVG.md §11).

Output is in **em units**, y-up, with the first baseline at ``y = 0`` — the same
convention as :mod:`lemur.typeset.latex`.
"""

from __future__ import annotations

import ctypes
import os
from dataclasses import dataclass

import numpy as np

# The bundled fonts (converted to TTF) are registered with fontconfig so Pango
# shapes with the *same* faces the deck ships — making output reproducible across
# machines and matching the browser emitter, regardless of what is installed.
_FONT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "fonts", "ttf")
_fonts_registered = False


def _register_app_fonts() -> None:
    global _fonts_registered
    if _fonts_registered:
        return
    _fonts_registered = True
    if not os.path.isdir(_FONT_DIR):
        return
    try:  # add to the *current* fontconfig config before Pango builds its fontmap
        fc = ctypes.CDLL("libfontconfig.so.1")
        fc.FcConfigGetCurrent.restype = ctypes.c_void_p
        fc.FcConfigAppFontAddDir.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
        fc.FcConfigAppFontAddDir(fc.FcConfigGetCurrent(), _FONT_DIR.encode("utf-8"))
    except Exception:  # pragma: no cover - falls back to system fonts
        pass

__all__ = ["ShapedText", "Cluster", "shape", "PangoUnavailable", "available", "font_exists", "resolve_family"]

#: Layout size used internally. Outlines are scaled afterwards, so this only
#: needs to be big enough that Pango's integer metrics stay precise.
_LAYOUT_SIZE = 128.0


class PangoUnavailable(RuntimeError):
    pass


@dataclass
class Cluster:
    subpaths: list[np.ndarray]
    closed: list[bool]
    text: str
    index: int  # byte offset into the source string
    line: int
    x_advance: float
    color: tuple[float, float, float] | None = None  # from markup, if any


@dataclass
class ShapedText:
    clusters: list[Cluster]
    line_height: float
    baselines: list[float]


_gi_cache: dict = {}


def _gi():
    if "mods" not in _gi_cache:
        try:
            import gi

            gi.require_version("Pango", "1.0")
            gi.require_version("PangoCairo", "1.0")
            from gi.repository import Pango, PangoCairo  # noqa: E402
            import cairo  # noqa: E402
        except Exception as exc:  # pragma: no cover - depends on system packages
            raise PangoUnavailable(
                "Text rendering needs PyGObject (Pango) and pycairo.\n"
                "Install them to build SVG decks."
            ) from exc
        _register_app_fonts()  # before any fontmap is created
        _gi_cache["mods"] = (Pango, PangoCairo, cairo)
    return _gi_cache["mods"]


def available() -> bool:
    try:
        _gi()
        return True
    except PangoUnavailable:
        return False


def font_exists(family: str) -> bool:
    """True if fontconfig can resolve ``family`` to that actual family."""
    Pango, PangoCairo, _ = _gi()
    fontmap = PangoCairo.FontMap.get_default()
    wanted = family.strip().lower()
    return any(f.get_name().lower() == wanted for f in fontmap.list_families())


def resolve_family(candidates: list[str]) -> str:
    """First installed family from ``candidates`` (last entry is the fallback)."""
    for c in candidates:
        try:
            if font_exists(c):
                return c
        except PangoUnavailable:
            return candidates[-1]
    return candidates[-1]


_xheight_cache: dict = {}


def _font_file(family: str) -> "str | None":
    """The font file for ``family``: a bundled face (``assets/fonts/ttf``) first,
    else whatever fontconfig matches (``fc-match``)."""
    import subprocess

    key = family.lower()
    if os.path.isdir(_FONT_DIR):
        for fn in sorted(os.listdir(_FONT_DIR)):
            if fn.endswith((".ttf", ".otf")) and "italic" not in fn:
                try:
                    out = subprocess.run(["fc-query", "-f", "%{family}\n", os.path.join(_FONT_DIR, fn)],
                                         capture_output=True, text=True, timeout=10).stdout
                except (OSError, subprocess.SubprocessError):
                    break
                if key in (f.strip().lower() for ln in out.splitlines() for f in ln.split(",")):
                    return os.path.join(_FONT_DIR, fn)
    try:
        out = subprocess.run(["fc-match", "-f", "%{file}", family], capture_output=True,
                             text=True, timeout=10).stdout.strip()
        return out or None
    except (OSError, subprocess.SubprocessError):
        return None


def x_height(family: str) -> "float | None":
    """The font's *metric* x-height in em (OS/2 ``sxHeight``) — what a browser's
    ``ex`` unit and MathJax's font matching use. None if unavailable."""
    if family in _xheight_cache:
        return _xheight_cache[family]
    val = None
    path = _font_file(family)
    try:
        import struct

        with open(path, "rb") as fh:
            data = fh.read()
        if data[:4] == b"ttcf":
            data_off = struct.unpack(">I", data[12:16])[0]
        else:
            data_off = 0
        n = struct.unpack(">H", data[data_off + 4:data_off + 6])[0]
        tables = {}
        for i in range(n):
            tag, _cs, off, _ln = struct.unpack(">4sIII", data[data_off + 12 + 16 * i:data_off + 28 + 16 * i])
            tables[tag] = off
        upem = struct.unpack(">H", data[tables[b"head"] + 18:tables[b"head"] + 20])[0]
        os2 = tables[b"OS/2"]
        if struct.unpack(">H", data[os2:os2 + 2])[0] >= 2:
            sx = struct.unpack(">h", data[os2 + 86:os2 + 88])[0]
            if sx > 0 and upem > 0:
                val = sx / upem
    except Exception:
        val = None
    _xheight_cache[family] = val
    return val


_metrics_cache: dict = {}


def font_metrics(font: str, weight: str | int = "normal", italic: bool = False) -> tuple[float, float]:
    """``(ascent, descent)`` of a font in **em** (baseline-relative), from the
    font's own metrics — independent of any particular string. Used to place text
    on a consistent baseline rather than by its glyphs' bounding box."""
    key = (font, str(weight), italic)
    if key not in _metrics_cache:
        Pango, PangoCairo, _ = _gi()
        ctx = PangoCairo.FontMap.get_default().create_context()
        desc = Pango.FontDescription()
        desc.set_family(font)
        desc.set_absolute_size(_LAYOUT_SIZE * Pango.SCALE)
        desc.set_weight(_pango_weight(_weight_value(weight)))
        desc.set_style(Pango.Style.ITALIC if italic else Pango.Style.NORMAL)
        m = ctx.get_metrics(desc, None)
        _metrics_cache[key] = (m.get_ascent() / Pango.SCALE / _LAYOUT_SIZE,
                               m.get_descent() / Pango.SCALE / _LAYOUT_SIZE)
    return _metrics_cache[key]


def _make_layout(ctx, text, font, size, weight, italic, line_spacing, align, width, markup):
    Pango, PangoCairo, cairo = _gi()
    layout = PangoCairo.create_layout(ctx)

    desc = Pango.FontDescription()
    desc.set_family(font)
    desc.set_absolute_size(size * Pango.SCALE)
    wv = _weight_value(weight)
    desc.set_weight(_pango_weight(wv))
    desc.set_style(Pango.Style.ITALIC if italic else Pango.Style.NORMAL)
    # The bundled faces are variable fonts whose default instance is ExtraLight;
    # pin the weight axis so the outlines are actually rendered at `wv`.
    if hasattr(desc, "set_variations"):
        desc.set_variations(f"wght={wv}")
    layout.set_font_description(desc)

    if markup:
        layout.set_markup(text, -1)
    else:
        layout.set_text(text, -1)

    layout.set_alignment(
        {"left": Pango.Alignment.LEFT, "center": Pango.Alignment.CENTER, "right": Pango.Alignment.RIGHT}[align]
    )
    if line_spacing is not None:
        layout.set_line_spacing(float(line_spacing))
    if width is not None:
        # Clamp to Pango's int32 width; a very large width just means "no wrap".
        layout.set_width(min(int(width * Pango.SCALE), 2**31 - 1))
        layout.set_wrap(Pango.WrapMode.WORD_CHAR)
    return layout


_WEIGHT_NAMES = {
    "thin": 100,
    "extralight": 200,
    "light": 300,
    "normal": 400,
    "regular": 400,
    "book": 400,
    "medium": 500,
    "semibold": 600,
    "bold": 700,
    "extrabold": 800,
    "heavy": 800,
    "black": 900,
}


def _weight_value(weight) -> int:
    if isinstance(weight, str):
        return _WEIGHT_NAMES.get(weight.lower().replace(" ", "").replace("-", ""), 400)
    return int(weight)


#: Valid PangoWeight enum values; an arbitrary weight (e.g. 650) is snapped to
#: the nearest for face matching, while set_variations carries the exact value.
_PANGO_WEIGHTS = (100, 200, 300, 350, 380, 400, 500, 600, 700, 800, 900, 1000)


def _pango_weight(wv: int):
    Pango, _, _ = _gi()
    return Pango.Weight(min(_PANGO_WEIGHTS, key=lambda v: abs(v - wv)))


_shape_cache: "dict" = {}
_SHAPE_CACHE_MAX = 20000


def shape(text: str, font: str = "sans", weight: "str | int" = "normal", italic: bool = False,
          line_spacing: "float | None" = None, align: str = "left",
          wrap_width: "float | None" = None, markup: bool = False) -> "ShapedText":
    """Shape ``text`` and return per-cluster outlines in **em units**, y-up,
    with the first baseline at ``y = 0``. ``wrap_width`` is in em units.

    Results are memoised in-process (a deck repeats its footer, bullets and
    common words many times); treat the returned outlines as read-only."""
    key = (text, font, str(weight), italic, line_spacing, align, wrap_width, markup)
    hit = _shape_cache.get(key)
    if hit is None:
        if len(_shape_cache) >= _SHAPE_CACHE_MAX:
            _shape_cache.clear()
        hit = _shape_cache[key] = _shape(text, font, weight, italic, line_spacing, align,
                                         wrap_width, markup)
    return hit


def _shape(
    text: str,
    font: str = "sans",
    weight: str | int = "normal",
    italic: bool = False,
    line_spacing: float | None = None,
    align: str = "left",
    wrap_width: float | None = None,
    markup: bool = False,
) -> ShapedText:
    """Shape ``text`` and return per-cluster outlines in **em units**, y-up,
    with the first baseline at ``y = 0``. ``wrap_width`` is in em units."""
    Pango, PangoCairo, cairo = _gi()

    surface = cairo.RecordingSurface(cairo.CONTENT_COLOR_ALPHA, None)
    ctx = cairo.Context(surface)
    # Unhinted outlines: shaping then does not depend on the layout size, so
    # results are scale-independent and safely cacheable.
    opts = cairo.FontOptions()
    opts.set_hint_style(cairo.HINT_STYLE_NONE)
    opts.set_hint_metrics(cairo.HINT_METRICS_OFF)
    opts.set_antialias(cairo.ANTIALIAS_GRAY)
    ctx.set_font_options(opts)

    w = wrap_width * _LAYOUT_SIZE if wrap_width is not None else None
    layout = _make_layout(ctx, text, font, _LAYOUT_SIZE, weight, italic, line_spacing, align, w, markup)
    plain = layout.get_text()

    # Whole-layout outline in one pass: this preserves shaping exactly.
    ctx.new_path()
    PangoCairo.layout_path(ctx, layout)
    subpaths, closed = _cairo_path_to_subpaths(ctx.copy_path())

    boxes = _cluster_boxes(layout, plain)
    clusters = _assign(subpaths, closed, boxes)
    _apply_markup_colors(layout, clusters)

    s = 1.0 / _LAYOUT_SIZE
    first_baseline = boxes[0].baseline if boxes else layout.get_baseline() / Pango.SCALE

    for cl in clusters:
        cl.subpaths = [_to_em(sp, s, first_baseline) for sp in cl.subpaths]
        cl.x_advance *= s

    n_lines = layout.get_line_count()
    baselines = []
    it = layout.get_iter()
    for _ in range(n_lines):
        baselines.append(-(it.get_baseline() / Pango.SCALE - first_baseline) * s)
        if not it.next_line():
            break
    _, log = layout.get_extents()
    line_h = (log.height / Pango.SCALE / max(n_lines, 1)) * s
    return ShapedText(clusters, line_h, baselines)


def _to_em(pts: np.ndarray, s: float, baseline: float) -> np.ndarray:
    """Layout px (y-down, origin top-left) -> em (y-up, origin on baseline)."""
    out = np.empty_like(pts)
    out[:, 0] = pts[:, 0] * s
    out[:, 1] = -(pts[:, 1] - baseline) * s
    return out


@dataclass
class _Box:
    x0: float
    x1: float
    baseline: float
    index: int
    text: str
    advance: float
    line_no: int


def _cluster_boxes(layout, plain: str) -> list[_Box]:
    """Logical extents of every cluster, in layout pixels."""
    Pango, _, _ = _gi()
    boxes: list[_Box] = []
    it = layout.get_iter()
    line_no = 0
    prev_baseline = None
    while True:
        _ink, log = it.get_cluster_extents()
        baseline = it.get_baseline() / Pango.SCALE
        if prev_baseline is not None and baseline != prev_baseline:
            line_no += 1
        prev_baseline = baseline
        boxes.append(
            _Box(
                x0=log.x / Pango.SCALE,
                x1=(log.x + log.width) / Pango.SCALE,
                baseline=baseline,
                index=it.get_index(),
                text="",
                advance=log.width / Pango.SCALE,
                line_no=line_no,
            )
        )
        if not it.next_cluster():
            break

    # A cluster covers the bytes up to the next cluster in *logical* order,
    # which is not iteration order once bidi is involved.
    raw = plain.encode("utf-8")
    starts = sorted({b.index for b in boxes} | {len(raw)})
    nxt = {s: starts[i + 1] for i, s in enumerate(starts[:-1])}
    for b in boxes:
        b.text = raw[b.index : nxt.get(b.index, len(raw))].decode("utf-8", "replace").replace("\n", "")
    return boxes


def _assign(subpaths, closed, boxes: list[_Box]) -> list[Cluster]:
    """Group outline subpaths into clusters.

    Pango hands back one merged outline. Splitting it per cluster (rather than
    per subpath) keeps multi-part glyphs together -- the dot of an 'i', an
    umlaut, the two strokes of an 'x' in some fonts.
    """
    baselines = sorted({b.baseline for b in boxes})
    by_line: dict[float, list[int]] = {bl: [] for bl in baselines}
    for i, b in enumerate(boxes):
        by_line[b.baseline].append(i)

    per_box: list[list[int]] = [[] for _ in boxes]
    for si, sp in enumerate(subpaths):
        x0, x1 = float(sp[:, 0].min()), float(sp[:, 0].max())
        bottom = float(sp[:, 1].max())
        # Glyph bottoms sit on (or just below) their own baseline.
        line = min(baselines, key=lambda bl: abs(bottom - bl))
        best, best_score = -1, None
        for bi in by_line[line]:
            b = boxes[bi]
            # Prefer real horizontal overlap; fall back to nearest centre for
            # glyphs that reach outside their advance (italics, swashes).
            score = (min(x1, b.x1) - max(x0, b.x0), -abs((x0 + x1) / 2 - (b.x0 + b.x1) / 2))
            if best_score is None or score > best_score:
                best, best_score = bi, score
        if best >= 0:
            per_box[best].append(si)

    return [
        Cluster(
            subpaths=[subpaths[i] for i in idxs],
            closed=[closed[i] for i in idxs],
            text=b.text,
            index=b.index,
            line=b.line_no,
            x_advance=b.advance,
        )
        for b, idxs in zip(boxes, per_box)
    ]


def _apply_markup_colors(layout, clusters: list[Cluster]) -> None:
    """Carry ``<span foreground=...>`` through to the glyph outlines."""
    Pango, _, _ = _gi()
    attrs = layout.get_attributes()
    if attrs is None:
        return
    ranges: list[tuple[int, int, tuple[float, float, float]]] = []
    it = attrs.get_iterator()
    while True:
        fg = it.get(Pango.AttrType.FOREGROUND)
        if fg is not None:
            try:
                c = fg.as_color().color
                start, end = it.range()
                ranges.append((start, end, (c.red / 65535, c.green / 65535, c.blue / 65535)))
            except Exception:  # pragma: no cover - Pango version differences
                pass
        if not it.next():
            break
    if not ranges:
        return
    for cl in clusters:
        for start, end, rgb in ranges:
            if start <= cl.index < end:
                cl.color = rgb
                break


def _cairo_path_to_subpaths(path) -> tuple[list[np.ndarray], list[bool]]:
    """cairo path -> ``3k+1`` cubic arrays."""
    _, _, cairo = _gi()

    subpaths: list[np.ndarray] = []
    closed: list[bool] = []
    cur: list[np.ndarray] = []
    start = np.zeros(2)
    pos = np.zeros(2)

    def flush(is_closed: bool) -> None:
        nonlocal cur
        if len(cur) >= 4:
            subpaths.append(np.array(cur))
            closed.append(is_closed)
        cur = []

    for typ, pts in path:
        if typ == cairo.PATH_MOVE_TO:
            flush(False)
            pos = np.array(pts[:2], dtype=float)
            start = pos.copy()
            cur = [pos.copy()]
        elif typ == cairo.PATH_LINE_TO:
            end = np.array(pts[:2], dtype=float)
            cur.extend([pos + (end - pos) / 3, pos + 2 * (end - pos) / 3, end])
            pos = end
        elif typ == cairo.PATH_CURVE_TO:
            c1 = np.array(pts[0:2], dtype=float)
            c2 = np.array(pts[2:4], dtype=float)
            end = np.array(pts[4:6], dtype=float)
            cur.extend([c1, c2, end])
            pos = end
        elif typ == cairo.PATH_CLOSE_PATH:
            if cur and not np.allclose(pos, start, atol=1e-9):
                cur.extend([pos + (start - pos) / 3, pos + 2 * (start - pos) / 3, start.copy()])
            flush(True)
            pos = start.copy()
    flush(False)
    return subpaths, closed
