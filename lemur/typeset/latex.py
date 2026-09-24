"""LaTeX maths -> vector outlines.

``latex`` produces a DVI, ``dvisvgm --no-fonts`` turns every glyph into an SVG
path, and we parse that back into the ``3k+1`` cubic representation. Nothing
about the result depends on a font (or MathJax) at display time — which is the
whole point: the deck becomes one self-contained HTML file with real TeX
typesetting. Mined from wanim (plans/Plan-SVG.md §11).

Output is in **em units** (1 em = the 10 pt document body), y-up, with the
baseline at ``y = 0`` — the same convention as :mod:`lemur.typeset.pango`, so
the layout engine can place text and maths identically.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from . import bezier as bz
from . import cache
from .svgpath import apply_transform, parse_path, parse_transform

__all__ = ["Glyph", "TexBox", "tex_glyphs", "tex_render", "tex_glyphs_marked", "tex_render_marked",
           "LatexError", "default_preamble", "wrap"]

SVG_NS = "{http://www.w3.org/2000/svg}"
XLINK_HREF = "{http://www.w3.org/1999/xlink}href"

#: dvisvgm emits SVG user units of 1/72 in; a 10 pt document has 1 em = 10 TeX pt.
_EM_IN_SVG_UNITS = 10.0 * 72.0 / 72.27

#: Fallback if the packaged preamble asset cannot be read.
_BUILTIN_PREAMBLE = (
    "\\usepackage[T1]{fontenc}\n"
    "\\usepackage{amsmath,amssymb,amsfonts,mathtools}\n"
    "\\usepackage{lmodern}\n"
    "\\usepackage{xcolor}\n"
    "\\setlength{\\jot}{2pt}\n"
)

_PREAMBLE_PATH = Path(__file__).resolve().parent.parent / "assets" / "latex" / "preamble.tex"

#: Set by the emitter from the active master's `preamble` (None → packaged file).
_preamble_override: "str | None" = None


def set_default_preamble(text: "str | None") -> None:
    """Override the preamble used by :func:`tex_glyphs` (a master's `preamble`).
    ``None`` restores the packaged default."""
    global _preamble_override
    _preamble_override = text


def default_preamble() -> str:
    """The active preamble: a master override if set, else the packaged file."""
    if _preamble_override is not None:
        text = _preamble_override
    else:
        try:
            text = _PREAMBLE_PATH.read_text(encoding="utf-8")
        except OSError:
            return _BUILTIN_PREAMBLE
    # Drop comment-only lines so the injected preamble stays tidy.
    lines = [ln for ln in text.splitlines() if not ln.lstrip().startswith("%")]
    return "\n".join(lines).strip() + "\n"


class LatexError(RuntimeError):
    pass


@dataclass
class Glyph:
    """One drawable piece of typeset output (a glyph, or a rule such as a
    fraction bar)."""

    subpaths: list[np.ndarray]
    closed: list[bool]
    key: str = ""
    fill: str | None = None
    meta: dict = field(default_factory=dict)


# --------------------------------------------------------------------------
# compilation
# --------------------------------------------------------------------------

_TEMPLATE = r"""\documentclass[preview,border=0pt,10pt]{standalone}
%(preamble)s
\begin{document}
%(body)s
\end{document}
"""


_BOX_RE = None


def _compile(body: str, preamble: str) -> str:
    """Run latex + dvisvgm, returning the SVG source.  Cached on disk.

    The SVG's coordinates are TeX's: the reference point of the typeset box at
    the origin, baseline on ``y = 0``. dvisvgm reads the box itself from the
    preview package (``--bbox=preview``) and reports it; it is kept as a leading
    ``<!--lmrbox w h d-->`` comment (TeX pt) so :func:`tex_box` can recover it —
    the box, not the ink, is what surrounding text is spaced against."""
    source = _TEMPLATE % {"preamble": preamble.strip(), "body": body}
    key = cache.key_for("latex-v2", source)
    hit = cache.get("latex", key)
    if hit is not None:
        return hit

    if shutil.which("latex") is None or shutil.which("dvisvgm") is None:
        raise LatexError(
            "LaTeX maths needs `latex` and `dvisvgm` on PATH.\n"
            "Install a TeX distribution with dvisvgm to build SVG decks."
        )

    with tempfile.TemporaryDirectory(prefix="lemur-tex-") as tmp:
        d = Path(tmp)
        (d / "doc.tex").write_text(source, encoding="utf-8")
        subprocess.run(
            ["latex", "-interaction=nonstopmode", "-halt-on-error", "-no-shell-escape", "doc.tex"],
            cwd=d,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if not (d / "doc.dvi").exists():
            log = (d / "doc.log").read_text(encoding="utf-8", errors="replace") if (d / "doc.log").exists() else ""
            raise LatexError(_latex_message(log, body))

        proc = subprocess.run(
            ["dvisvgm", "--no-fonts", "--bbox=preview", "--precision=6", "-o", "doc.svg", "doc.dvi"],
            cwd=d,
            capture_output=True,
            text=True,
            timeout=120,
        )
        svg_path = d / "doc.svg"
        if not svg_path.exists():
            raise LatexError(f"dvisvgm failed:\n{proc.stderr.strip()}")
        svg = svg_path.read_text(encoding="utf-8")
        import re

        global _BOX_RE
        if _BOX_RE is None:
            _BOX_RE = re.compile(r"width=([-\d.]+)pt, height=([-\d.]+)pt, depth=([-\d.]+)pt")
        m = _BOX_RE.search((proc.stdout or "") + (proc.stderr or ""))
        if m:
            svg = f"<!--lmrbox {m.group(1)} {m.group(2)} {m.group(3)}-->" + svg

    cache.put("latex", key, svg)
    return svg


def _latex_message(log: str, body: str) -> str:
    """Pull the useful lines out of a LaTeX log."""
    lines = log.splitlines()
    errors = [ln for ln in lines if ln.startswith("!")]
    context = []
    for i, ln in enumerate(lines):
        if ln.startswith("!"):
            context.extend(lines[i : i + 4])
    detail = "\n".join(context or errors or lines[-15:])
    return f"LaTeX failed on:\n  {body}\n\n{detail}"


# --------------------------------------------------------------------------
# parsing
# --------------------------------------------------------------------------


def _walk(node, matrix, defs, fill, out: list[Glyph]) -> None:
    for child in node:
        tag = child.tag.replace(SVG_NS, "")
        if tag == "defs":
            continue  # already harvested by _collect_defs; drawing them would double up
        m = matrix @ parse_transform(child.get("transform"))
        f = child.get("fill", fill)

        if tag == "g":
            _walk(child, m, defs, f, out)
        elif tag == "path" and child.get("d"):
            subs, closed = parse_path(child.get("d"))
            out.append(_make_glyph(subs, closed, m, f))
        elif tag == "use":
            ref = (child.get(XLINK_HREF) or child.get("href") or "").lstrip("#")
            proto = defs.get(ref)
            if proto is None:
                continue
            t = np.eye(3)
            t[0, 2] = float(child.get("x", 0) or 0)
            t[1, 2] = float(child.get("y", 0) or 0)
            subs, closed = proto
            out.append(_make_glyph(subs, closed, m @ t, f, ref=ref))
        elif tag == "rect":
            x, y = float(child.get("x", 0)), float(child.get("y", 0))
            w, h = float(child.get("width", 0)), float(child.get("height", 0))
            if w <= 0 or h <= 0:
                continue
            corners = np.array([[x, y], [x + w, y], [x + w, y + h], [x, y + h], [x, y]])
            out.append(_make_glyph([bz.line_handles(corners)], [True], m, f, ref=f"rect{w:.4f}x{h:.4f}"))
        elif tag == "svg":
            _walk(child, m, defs, f, out)


def _make_glyph(subs, closed, matrix, fill, ref: str | None = None) -> Glyph:
    # SVG is y-down; flip once, here, so everything downstream is y-up.
    flip = np.diag([1.0, -1.0, 1.0])
    M = flip @ matrix
    moved = [apply_transform(M, sp) / _EM_IN_SVG_UNITS for sp in subs]
    return Glyph(moved, list(closed), key=ref or "", fill=fill)


def _collect_defs(root) -> dict:
    defs = {}
    for el in root.iter():
        if el.tag.replace(SVG_NS, "") == "path" and el.get("id") and el.get("d"):
            defs[el.get("id")] = parse_path(el.get("d"))
    return defs


#: Unicode symbols authors paste into maths (MathJax accepted them; pdfTeX with
#: T1 does not). Each maps to a command that works in maths *and* text mode.
_UNICODE_TEX = {
    # relations
    "≤": r"\leq", "≥": r"\geq", "≠": r"\neq", "≈": r"\approx", "≡": r"\equiv",
    "∼": r"\sim", "≃": r"\simeq", "≅": r"\cong", "∝": r"\propto", "≪": r"\ll",
    "≫": r"\gg", "≔": r"\coloneqq", "⊥": r"\perp", "∣": r"\mid", "∥": r"\parallel",
    # sets and logic
    "∈": r"\in", "∉": r"\notin", "∋": r"\ni", "⊂": r"\subset", "⊃": r"\supset",
    "⊆": r"\subseteq", "⊇": r"\supseteq", "∪": r"\cup", "∩": r"\cap",
    "∅": r"\emptyset", "∀": r"\forall", "∃": r"\exists", "∄": r"\nexists",
    "¬": r"\neg", "∧": r"\wedge", "∨": r"\vee", "⊕": r"\oplus", "⊗": r"\otimes",
    "∘": r"\circ", "⊤": r"\top", "⊢": r"\vdash", "⊨": r"\models",
    # arrows
    "→": r"\to", "←": r"\leftarrow", "↔": r"\leftrightarrow", "⇒": r"\Rightarrow",
    "⇐": r"\Leftarrow", "⇔": r"\Leftrightarrow", "↦": r"\mapsto", "↑": r"\uparrow",
    "↓": r"\downarrow", "⟶": r"\longrightarrow", "⟹": r"\Longrightarrow",
    # operators and big operators
    "×": r"\times", "·": r"\cdot", "⋅": r"\cdot", "÷": r"\div", "±": r"\pm",
    "∓": r"\mp", "∗": r"\ast", "−": "-", "∑": r"\sum", "∏": r"\prod",
    "∫": r"\int", "∮": r"\oint", "∂": r"\partial", "∇": r"\nabla", "√": r"\surd",
    "∞": r"\infty", "…": r"\ldots", "⋯": r"\cdots", "⋮": r"\vdots", "⋱": r"\ddots",
    "′": "'", "″": "''", "⟨": r"\langle", "⟩": r"\rangle", "⌈": r"\lceil",
    "⌉": r"\rceil", "⌊": r"\lfloor", "⌋": r"\rfloor", "°": r"^{\circ}",
    # letter-like
    "ℓ": r"\ell", "ℏ": r"\hbar", "ℵ": r"\aleph", "℘": r"\wp",
    "ℜ": r"\Re", "ℑ": r"\Im", "ℝ": r"\mathbb{R}", "ℕ": r"\mathbb{N}",
    "ℤ": r"\mathbb{Z}", "ℚ": r"\mathbb{Q}", "ℂ": r"\mathbb{C}", "ℙ": r"\mathbb{P}",
    "ℰ": r"\mathcal{E}", "ℱ": r"\mathcal{F}", "ℋ": r"\mathcal{H}", "ℒ": r"\mathcal{L}",
    "ℳ": r"\mathcal{M}", "ℬ": r"\mathcal{B}", "ℐ": r"\mathcal{I}", "ℛ": r"\mathcal{R}",
}

_GREEK = (
    "alpha beta gamma delta epsilon zeta eta theta iota kappa lambda mu nu xi "
    "omicron pi rho varsigma sigma tau upsilon phi chi psi omega"
).split()
for _i, _n in enumerate(_GREEK):
    _lo = chr(0x3B1 + _i)
    _UNICODE_TEX[_lo] = "o" if _n == "omicron" else "\\" + _n
    if _n not in ("varsigma",):
        _up = chr(0x391 + _i)
        _UNICODE_TEX[_up] = (
            "\\" + _n.capitalize()
            if _n in ("gamma", "delta", "theta", "lambda", "xi", "pi", "sigma", "upsilon", "phi", "psi", "omega")
            else {"alpha": "A", "beta": "B", "epsilon": "E", "zeta": "Z", "eta": "H", "iota": "I",
                  "kappa": "K", "mu": "M", "nu": "N", "omicron": "O", "rho": "P", "tau": "T", "chi": "X"}[_n]
        )
_UNICODE_TEX.update({"ϵ": r"\epsilon", "ε": r"\varepsilon", "ϑ": r"\vartheta", "ϕ": r"\phi",
                     "φ": r"\varphi", "ϱ": r"\varrho", "ϖ": r"\varpi"})

#: Mathematical Alphanumeric Symbols (U+1D400…) style word → the maths alphabet.
_MATH_ALPHABETS = (
    ("BOLD ITALIC", r"\boldsymbol{%s}"), ("BOLD SCRIPT", r"\mathcal{%s}"),
    ("BOLD FRAKTUR", r"\mathfrak{%s}"), ("SANS-SERIF BOLD ITALIC", r"\mathsf{%s}"),
    ("SANS-SERIF BOLD", r"\mathsf{%s}"), ("SANS-SERIF ITALIC", r"\mathsf{%s}"),
    ("SANS-SERIF", r"\mathsf{%s}"), ("DOUBLE-STRUCK", r"\mathbb{%s}"),
    ("FRAKTUR", r"\mathfrak{%s}"), ("SCRIPT", r"\mathcal{%s}"),
    ("MONOSPACE", r"\mathtt{%s}"), ("BOLD", r"\mathbf{%s}"), ("ITALIC", "%s"),
)


def _unicode_char_tex(ch: str) -> "str | None":
    tex = _UNICODE_TEX.get(ch)
    if tex is not None:
        return tex
    if not 0x1D400 <= ord(ch) <= 0x1D7FF:
        return None
    import unicodedata

    name = unicodedata.name(ch, "")
    if not name.startswith("MATHEMATICAL "):
        return None
    rest = name[len("MATHEMATICAL "):]
    for style, fmt in _MATH_ALPHABETS:
        if rest.startswith(style + " "):
            rest = rest[len(style) + 1:]
            break
    else:
        fmt = "%s"
    # the base symbol: a Latin letter, a digit, or a Greek letter
    parts = rest.split()
    if len(parts) == 2 and parts[0] in ("CAPITAL", "SMALL") and len(parts[1]) == 1:
        base = parts[1] if parts[0] == "CAPITAL" else parts[1].lower()
    elif len(parts) == 2 and parts[0] == "DIGIT":
        base = str(["ZERO", "ONE", "TWO", "THREE", "FOUR", "FIVE", "SIX", "SEVEN", "EIGHT", "NINE"].index(parts[1]))
    elif len(parts) >= 2 and parts[0] in ("CAPITAL", "SMALL"):
        greek = parts[-1].lower()
        if greek not in _GREEK:
            return None
        base = "\\" + (greek.capitalize() if parts[0] == "CAPITAL" else greek)
        if fmt in (r"\mathbf{%s}", r"\mathsf{%s}"):
            fmt = r"\boldsymbol{%s}"
    else:
        return None
    return fmt % base


def unicode_to_tex(body: str) -> str:
    """Rewrite the Unicode maths symbols LaTeX cannot read into commands.

    Each replacement is wrapped in ``\\ensuremath{…}``, which is safe inside a
    ``\\text{…}`` and, in maths mode, expands to its bare argument — so a
    relation keeps its spacing and ``∑_i`` keeps its limits. Plain Latin-1 text
    (``ä``, ``é``) is left to inputenc/T1."""
    if body.isascii():
        return body
    out = []
    for ch in body:
        tex = _unicode_char_tex(ch) if ord(ch) > 0x7F else None
        out.append(ch if tex is None else "\\ensuremath{%s}" % tex)
    return "".join(out)


@dataclass
class TexBox:
    """TeX's box of a typeset formula, in em (1 em = 10pt): it spans
    ``x ∈ [0, width]`` and ``y ∈ [-depth, height]`` around the baseline."""

    width: float
    height: float
    depth: float


def tex_render(body: str, preamble: str | None = None) -> tuple:
    """Typeset ``body`` → ``(glyphs, box)``: the pieces (em units, y-up, baseline
    at ``y = 0``, box origin at ``x = 0``) and TeX's :class:`TexBox` (``None``
    if dvisvgm did not report one)."""
    body = unicode_to_tex(body)
    svg = _compile(body, preamble if preamble is not None else default_preamble())
    box = None
    if svg.startswith("<!--lmrbox "):
        head, _, svg = svg.partition("-->")
        try:
            w, h, dp = (float(v) for v in head[len("<!--lmrbox "):].split())
            box = TexBox(w / 10.0, h / 10.0, dp / 10.0)   # TeX pt → em of the 10pt body
        except ValueError:
            box = None
    return _parse_glyphs(svg), box


def tex_glyphs(body: str, preamble: str | None = None) -> list[Glyph]:
    """Typeset ``body`` and return its pieces, in em units with y-up and the
    baseline at ``y = 0``."""
    return tex_render(body, preamble)[0]


def _parse_glyphs(svg: str) -> list[Glyph]:
    root = ET.fromstring(svg)
    defs = _collect_defs(root)

    out: list[Glyph] = []
    _walk(root, np.eye(3), defs, None, out)
    out = [g for g in out if any(len(sp) for sp in g.subpaths)]

    # dvisvgm emits in document order (TeX's left-to-right), which per-symbol
    # indexing and progressive `Write` both rely on.  Keep it.
    for g in out:
        if not g.key:
            g.key = geometry_key(g.subpaths)
    return out


def geometry_key(subpaths: list[np.ndarray], places: int = 4) -> str:
    """Translation-invariant hash of a shape, used to share glyph outlines."""
    if not subpaths:
        return "empty"
    origin = subpaths[0][0]
    import hashlib

    h = hashlib.blake2b(digest_size=12)
    for sp in subpaths:
        h.update(np.round(sp - origin, places).tobytes())
        h.update(b"|")
    return h.hexdigest()


def _colorize(body: str, marks: list) -> tuple:
    """Wrap each mark's byte range in a unique `\\color` sentinel so its glyphs
    can be found in the dvisvgm output. Returns ``(colored_tex, {rgb: name})``."""
    raw = body.encode("utf-8")
    sent: dict = {}
    out = bytearray()
    pos = 0
    for i, m in enumerate(sorted(marks, key=lambda m: m.get("from", 0))):
        f, t = int(m.get("from", 0)), int(m.get("to", 0))
        if f < pos or t <= f or t > len(raw):
            continue  # skip overlapping/degenerate ranges
        rgb = (1, 1, i + 1)  # near-black, unique, absent from normal maths
        sent[rgb] = m.get("name")
        out += raw[pos:f]
        out += ("{\\color[RGB]{%d,%d,%d}" % rgb).encode("utf-8")
        out += raw[f:t]
        out += b"}"
        pos = t
    out += raw[pos:]
    return out.decode("utf-8", "replace"), sent


def _parse_rgb(fill):
    if not fill or not isinstance(fill, str) or len(fill) != 7 or fill[0] != "#":
        return None
    try:
        return (int(fill[1:3], 16), int(fill[3:5], 16), int(fill[5:7], 16))
    except ValueError:
        return None


def tex_glyphs_marked(body: str, marks: list, mode: str = "display", preamble: str | None = None):
    """Like :func:`tex_glyphs` but also tag each glyph that belongs to a `\\mk`
    mark with ``g.meta["mark"] = name`` (via a colour sentinel), then reset it to
    the normal colour. Returns the glyph list."""
    return tex_render_marked(body, marks, mode, preamble)[0]


def tex_render_marked(body: str, marks: list, mode: str = "display", preamble: str | None = None):
    """:func:`tex_glyphs_marked`, also returning TeX's box: ``(glyphs, box)``."""
    if not marks:
        return tex_render(wrap(body, mode), preamble)
    colored, sent = _colorize(body, marks)
    glyphs, box = tex_render(wrap(colored, mode), preamble)
    for g in glyphs:
        name = sent.get(_parse_rgb(g.fill))
        if name:
            g.meta["mark"] = name
            g.fill = None  # render in the normal maths colour, not the sentinel
    return glyphs, box


def wrap(body: str, mode: str = "display") -> str:
    """Put ``body`` into the right maths mode.

    Multi-line input (a ``\\\\`` line break, or ``&`` alignment marks) is
    wrapped in ``aligned`` automatically.
    """
    if mode == "text":
        return body
    if mode == "display":
        body = _inner_display_envs(body)
        top = _top_level(body)
        if "&" in top:
            inner = rf"\begin{{aligned}}{body}\end{{aligned}}"
        elif r"\\" in top:
            # MathJax centres bare `\\`-separated lines; `gathered` does the same.
            inner = rf"\begin{{gathered}}{body}\end{{gathered}}"
        else:
            inner = body
        # display *style* in a tight box (not a `\[…\]` paragraph), so TeX's
        # box — height, depth, width — is the formula's own, like MathJax's
        return rf"\hbox{{\(\displaystyle {inner}\)}}"
    # a box: TeX must never break an inline formula across lines here
    return rf"\hbox{{\({body}\)}}"


#: Top-level display environments (illegal inside `\[…\]`) → their inner-mode
#: equivalents. MathJax accepted `\[\begin{align}…\end{align}\]`; amsmath does not.
#: Numbering is dropped, as MathJax (tags: none) did.
_DISPLAY_ENVS = {
    "align": "aligned", "align*": "aligned", "flalign": "aligned", "flalign*": "aligned",
    "alignat": "alignedat", "alignat*": "alignedat", "gather": "gathered", "gather*": "gathered",
    "multline": "gathered", "multline*": "gathered",
    "eqnarray": ("array}{rcl", "array"), "eqnarray*": ("array}{rcl", "array"),
    "equation": None, "equation*": None, "displaymath": None,
}

_ENV_RE = None


def _inner_display_envs(body: str) -> str:
    import re

    global _ENV_RE
    if _ENV_RE is None:
        names = "|".join(re.escape(n) for n in sorted(_DISPLAY_ENVS, key=len, reverse=True))
        _ENV_RE = re.compile(r"\\(begin|end)\{(" + names + r")\}")

    def sub(m):
        repl = _DISPLAY_ENVS[m.group(2)]
        if repl is None:
            return ""
        if isinstance(repl, tuple):
            repl = repl[0] if m.group(1) == "begin" else repl[1]
        return "\\%s{%s}" % (m.group(1), repl)

    out, count = _ENV_RE.subn(sub, body)
    if count:
        # numbering commands are an error inside the inner environments
        out = re.sub(r"\\(?:label|tag\*?)\{[^{}]*\}|\\(?:nonumber|notag)\b", "", out)
    return out


def _top_level(body: str) -> str:
    """``body`` with every brace group and ``\\begin…\\end`` environment blanked,
    so a ``&``/``\\\\`` inside a matrix or ``cases`` is not mistaken for a
    top-level alignment."""
    out = []
    depth = 0  # brace depth
    env = 0  # environment depth
    i = 0
    n = len(body)
    while i < n:
        c = body[i]
        if c == "\\":
            if body.startswith("\\begin{", i):
                env += 1
                i = body.find("}", i) + 1 or n
                continue
            if body.startswith("\\end{", i):
                env = max(0, env - 1)
                i = body.find("}", i) + 1 or n
                continue
            tok = body[i : i + 2]
            if depth == 0 and env == 0:
                out.append(tok if tok == "\\\\" else " ")  # `\&` is a literal, not a tab
            i += 2
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth = max(0, depth - 1)
        elif depth == 0 and env == 0:
            out.append(c)
        i += 1
    return "".join(out)
