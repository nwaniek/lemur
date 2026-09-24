"""The design box the SVG emitter lays out into.

Two representations, one vocabulary:

* :class:`Style` — the **user-facing** design box, a class with fields (the
  ``clean`` theme by default). Users subclass a shipped theme in their
  ``style.py`` (see :mod:`lemur.style`); the built-in themes live in
  ``lemur/themes/*.py`` as :class:`Style` subclasses.
* :class:`Design` — the **resolved** struct the emitter reads: the same fields,
  flat and normalised (fonts as tuples, transition as a dict, preamble as an
  absolute path). Built once per deck by :func:`resolve_design`.

The page-master / Beamer separation of *where things go* (regions) from *what
flows in* (Plan-SVG §6).
"""

from __future__ import annotations

import os
from dataclasses import dataclass

__all__ = ["Region", "Style", "Design", "resolve_design", "default_design",
           "theme_names", "theme_design", "find_theme_dir", "css_theme_design"]

THEMES_PKG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "themes")


def theme_names() -> list:
    """The names of the shipped SVG themes (``lemur/themes/<name>.py``, each a
    :class:`Style` subclass)."""
    try:
        return sorted(f[:-3] for f in os.listdir(THEMES_PKG_DIR)
                      if f.endswith(".py") and not f.startswith("_"))
    except OSError:
        return []


def theme_design(name: str) -> "Design | None":
    """Resolve a shipped theme's ``Style`` to a :class:`Design`, or None if there
    is no such theme."""
    import importlib
    try:
        mod = importlib.import_module(f"{__package__}.themes.{name}")
    except ModuleNotFoundError:
        return None
    style = getattr(mod, "Style", None)
    return resolve_design(style) if style is not None else None


@dataclass
class Region:
    x: float
    y: float
    w: float
    h: "float | None"  # None means "auto" (grow to content)


class Style:
    """A deck's design box as a **class with fields** — the user-facing way to
    style a deck (in a ``style.py``). The defaults are the ``clean`` theme;
    subclass a shipped theme and override a few fields::

        from lemur.themes import journal
        from lemur.style import Style, Region

        class Style(journal.Style):
            accent = "#c8a24a"
            body_region = Region(80, 320, 1760, 610)
            transition = ("push", "rise")

    :func:`resolve_design` turns it into a :class:`Design`."""

    # design box (px)
    width = 1920
    height = 1080
    # ground & ink
    bg = "#ffffff"
    title = "#232629"
    body = "#232629"
    math = "#232629"
    caption = "#666666"
    accent = "#2e5e6e"
    rule = "#d5d8db"
    # code
    code = "#232629"            # code text
    code_bg = "#f2f2f2"         # code panel / inline-code chip background
    code_keyword = "#a3562a"
    code_string = "#3a7d44"
    code_number = "#7a4b94"
    code_comment = "#8a9099"
    code_function = "#2e5e6e"
    code_type = "#2e6e5e"
    code_highlight = "#f0c828"  # per-step line-highlight background
    # fonts (a tuple of families, or a comma-separated string)
    serif = ("Source Sans 3", "DejaVu Sans", "sans-serif")
    mono = ("JetBrains Mono", "DejaVu Sans Mono", "monospace")
    # type sizes (design-box px). The defaults are the HTML deck's proportions
    # of a 40px body: title 1.35em, code 0.62em, table 0.85em, caption 0.7em.
    title_size = 54
    body_size = 40
    math_size = 40
    code_size = 25
    table_size = 34
    caption_size = 28
    title_weight = 650
    title_spacing = -0.01       # heading letter-spacing (em)
    title_rule = 3              # accent underline height (0 = none)
    line_height = 1.45          # running text (paragraphs, list items), × font size
    # the title slide (cover)
    cover_title_scale = 1.7     # title size in body ems
    cover_rule = False          # a short accent rule between subtitle and byline
    cover_caps = False          # an uppercase, letter-spaced, smaller byline
    # regions: Region(x, y, w, h); h=None means auto (grow to content)
    # The body starts right under the title (and its rule); ``body_region.y`` is
    # the earliest it may start — raise it to reserve room, e.g. for a header bar.
    title_region = Region(96, 72, 1728, None)
    body_region = Region(96, 150, 1728, 858)
    # behaviour
    transition = None           # e.g. ("push", "rise") — across, step
    preamble = None             # LaTeX preamble path (relative to the style.py)


# The resolved design: the same field names as Style, flat and normalised. The
# emitter reads only this; treat it as read-only (a snapshot of a Style).
@dataclass
class Design:
    width: int
    height: int
    bg: str
    title: str
    body: str
    math: str
    caption: str
    accent: str
    rule: str
    code: str
    code_bg: str
    code_keyword: str
    code_string: str
    code_number: str
    code_comment: str
    code_function: str
    code_type: str
    code_highlight: str
    serif: tuple
    mono: tuple
    title_size: float
    body_size: float
    math_size: float
    code_size: float
    table_size: float
    caption_size: float
    title_weight: float
    title_spacing: float
    title_rule: float
    line_height: float
    cover_title_scale: float
    cover_rule: bool
    cover_caps: bool
    title_region: Region
    body_region: Region
    transition: "dict | None"   # {"across":…, "step":…}
    preamble: "str | None"      # absolute path to a LaTeX preamble, or None

    def preamble_text(self) -> "str | None":
        """The preamble file's contents, or None to use the packaged default."""
        if not self.preamble:
            return None
        try:
            return open(self.preamble, encoding="utf-8").read()
        except OSError:
            return None


def _families(v) -> tuple:
    return tuple(f.strip() for f in v.split(",")) if isinstance(v, str) else tuple(v)


def _transition(t) -> "dict | None":
    if not t:
        return None
    if isinstance(t, dict):
        return dict(t)
    across, *rest = t if isinstance(t, (list, tuple)) else (t,)
    return {"across": across, "step": rest[0] if rest else "fade"}


def resolve_design(style, base_dir: str = ".") -> Design:
    """Snapshot a :class:`Style` (class or instance) into a :class:`Design`,
    normalising fonts (→ tuple), the transition (→ dict), and the preamble path
    (→ absolute, relative to ``base_dir`` = the style.py's folder)."""
    s = style() if isinstance(style, type) else style
    pre = s.preamble
    if pre and not os.path.isabs(pre):
        pre = os.path.join(base_dir, pre)
    return Design(
        width=int(s.width), height=int(s.height),
        bg=s.bg, title=s.title, body=s.body, math=s.math, caption=s.caption,
        accent=s.accent, rule=s.rule, code=s.code, code_bg=s.code_bg,
        code_keyword=s.code_keyword, code_string=s.code_string, code_number=s.code_number,
        code_comment=s.code_comment, code_function=s.code_function, code_type=s.code_type,
        code_highlight=s.code_highlight,
        serif=_families(s.serif), mono=_families(s.mono),
        title_size=float(s.title_size), body_size=float(s.body_size), math_size=float(s.math_size),
        code_size=float(s.code_size), table_size=float(s.table_size), caption_size=float(s.caption_size),
        title_weight=float(s.title_weight), title_rule=float(s.title_rule),
        title_spacing=float(getattr(s, "title_spacing", 0.0)),
        line_height=float(getattr(s, "line_height", 1.45)),
        cover_title_scale=float(getattr(s, "cover_title_scale", 1.7)),
        cover_rule=bool(getattr(s, "cover_rule", False)),
        cover_caps=bool(getattr(s, "cover_caps", False)),
        title_region=s.title_region, body_region=s.body_region,
        transition=_transition(s.transition), preamble=pre,
    )


def default_design() -> Design:
    """The default design — the built-in :class:`Style` (the ``clean`` theme)."""
    return resolve_design(Style)


# --------------------------------------------------------------------------
# deck-local themes: `!theme <name>` → themes/<name>/{style.py,theme.css}
# --------------------------------------------------------------------------


def theme_search_dirs(doc_dir: str, extra: "list | None" = None) -> list:
    """Where a named deck theme is looked up, in order — the same order the HTML
    emitter used: explicit dirs, ``$LEMUR_THEMES`` (os.pathsep-separated), then
    ``themes/`` next to the document."""
    dirs = list(extra or [])
    env = os.environ.get("LEMUR_THEMES", "")
    dirs += [d for d in env.split(os.pathsep) if d]
    dirs.append(os.path.join(doc_dir, "themes"))
    return dirs


def find_theme_dir(name: str, doc_dir: str, extra: "list | None" = None) -> "str | None":
    """The folder of a deck-local theme ``name`` (holding a ``style.py`` or a
    ``theme.css``), or None. A name with a path separator is a direct path."""
    if not name:
        return None
    cands = ([os.path.join(doc_dir, name), name] if (os.sep in name or "/" in name)
             else [os.path.join(d, name) for d in theme_search_dirs(doc_dir, extra)])
    for c in cands:
        if os.path.isfile(os.path.join(c, "style.py")) or os.path.isfile(os.path.join(c, "theme.css")):
            return os.path.abspath(c)
    return None


_CSS_VAR = None


def css_tokens(text: str) -> dict:
    """The ``--lmr-*`` custom properties declared in a stylesheet's ``:root``
    blocks (later declarations win, as in CSS)."""
    import re

    global _CSS_VAR
    if _CSS_VAR is None:
        _CSS_VAR = re.compile(r"(--lmr-[\w-]+)\s*:\s*([^;{}]+);")
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    toks: dict = {}
    for block in re.findall(r":root\s*\{([^}]*)\}", text):
        for k, v in _CSS_VAR.findall(block):
            toks[k] = v.strip()
    return toks


def _css_resolve(v: str, toks: dict, depth: int = 0) -> str:
    """Expand ``var(--x)`` / ``var(--x, fallback)`` references."""
    import re

    if depth > 8 or "var(" not in v:
        return v

    def sub(m):
        name, fb = m.group(1), m.group(2)
        if name in toks:
            return _css_resolve(toks[name], toks, depth + 1)
        return (fb or "").strip()

    return re.sub(r"var\(\s*(--[\w-]+)\s*(?:,\s*([^()]*))?\)", sub, v)


def _css_families(v: str) -> tuple:
    fams = tuple(f.strip().strip("\"'") for f in v.split(",") if f.strip())
    return tuple(f for f in fams if f not in ("system-ui",)) or fams


def _css_px(v: str, base: float) -> "float | None":
    import re

    m = re.match(r"\s*(-?[\d.]+)\s*(px|em|rem)?\s*$", v or "")
    if not m:
        return None
    x = float(m.group(1))
    return x * base if m.group(2) in ("em", "rem") else x


def _css_color(v: str) -> "str | None":
    import re

    v = (v or "").strip()
    if re.fullmatch(r"#[0-9a-fA-F]{3,8}|[a-zA-Z]+|rgba?\([^)]*\)", v):
        return v
    return None


def css_theme_design(css_path: str, base: "type | None" = None) -> Design:
    """Derive a :class:`Design` from an HTML-emitter ``theme.css`` — the colour,
    font and size tokens (``--lmr-*``) mapped onto the :class:`Style` fields — so
    a deck with a custom CSS theme renders to SVG without being ported. Sizes
    scale from ``--lmr-font-size`` relative to the 40px base, keeping the
    proportions the ``clean`` design uses. Structural CSS rules (selectors other
    than ``:root``) have no SVG equivalent and are ignored."""
    with open(css_path, encoding="utf-8") as fh:
        text = fh.read()
    # the documented defaults (tokens.css), overridden by the theme
    defaults_path = os.path.join(os.path.dirname(THEMES_PKG_DIR), "assets", "tokens.css")
    toks: dict = {}
    try:
        with open(defaults_path, encoding="utf-8") as fh:
            toks.update(css_tokens(fh.read()))
    except OSError:
        pass
    toks.update(css_tokens(text))

    def tok(name):
        v = toks.get(name)
        return _css_resolve(v, toks) if v is not None else None

    B = base or Style
    fields: dict = {}
    body = _css_px(tok("--lmr-font-size") or "", 40.0) or float(B.body_size)
    k = body / 40.0
    fields.update(body_size=body, math_size=body, code_size=0.62 * body,
                  table_size=0.85 * body, caption_size=0.7 * body)
    h2 = _css_px(tok("--lmr-h2-size") or "", body)
    fields["title_size"] = h2 if h2 else B.title_size * k
    colors = {"bg": "--lmr-bg", "body": "--lmr-ink", "math": "--lmr-ink", "code": "--lmr-ink",
              "title": "--lmr-heading", "accent": "--lmr-accent", "caption": "--lmr-muted",
              "rule": "--lmr-rule", "code_bg": "--lmr-code-bg", "code_keyword": "--lmr-code-kw",
              "code_string": "--lmr-code-str", "code_number": "--lmr-code-num",
              "code_comment": "--lmr-code-comment", "code_function": "--lmr-code-fn",
              "code_type": "--lmr-code-type"}
    for field, name in colors.items():
        c = _css_color(tok(name) or "")
        if c:
            fields[field] = c
    if tok("--lmr-font"):
        fields["serif"] = _css_families(tok("--lmr-font"))
    if tok("--lmr-mono"):
        fields["mono"] = _css_families(tok("--lmr-mono"))
    try:
        fields["title_weight"] = float(tok("--lmr-heading-weight") or B.title_weight)
    except ValueError:
        pass
    sp = _css_px(tok("--lmr-heading-spacing") or "", 1.0)
    if sp is not None:
        fields["title_spacing"] = sp
    rule = tok("--lmr-heading-rule")
    if rule is not None:
        w = _css_px((rule.split() or ["0"])[0], body)
        fields["title_rule"] = 0.0 if (w is None or "none" in rule) else w
    px, py = _css_px(tok("--lmr-pad-x") or "", body), _css_px(tok("--lmr-pad-y") or "", body)
    if px is not None or py is not None:
        px = B.title_region.x if px is None else px
        py = B.title_region.y if py is None else py
        W = B.width
        tr, br = B.title_region, B.body_region
        fields["title_region"] = Region(px, py, W - 2 * px, tr.h)
        fields["body_region"] = Region(px, br.y + (py - tr.y), W - 2 * px, br.h)
    # the few structural cover rules the shipped themes use (journal's treatment)
    import re
    flat = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    for sel, body_css in re.findall(r"([^{}]+)\{([^}]*)\}", flat):
        sel = " ".join(sel.split())
        if re.search(r"\.cover\s+h1$", sel):
            m = re.search(r"font-size\s*:\s*([\d.]+)em", body_css)
            if m:
                fields["cover_title_scale"] = float(m.group(1))
        elif sel.endswith(".lmr-title-rule") and re.search(r"display\s*:\s*block", body_css):
            fields["cover_rule"] = True
        elif sel.endswith(".lmr-byline") and "uppercase" in body_css:
            fields["cover_caps"] = True
    cls = type("CssStyle", (B,), fields)
    return resolve_design(cls, base_dir=os.path.dirname(os.path.abspath(css_path)))
