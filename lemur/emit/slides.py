#!/usr/bin/env python3
"""lmr2slides — the HTML slide-deck emitter.

Consumes a lemur document (a `.lmr`, which it parses via `lemur.parser`, or a
neutral AST it validates via `lemur.ast`) and writes a self-contained folder: index.html,
slides.css (base + theme), runtime.js, the bundled fonts, and any figures. This
is one of the AST's emitters — a sibling of lmr2tex — and owns everything about
*packaging a browser deck*; the parser (lemur.parser) knows nothing about it.

Rendering still happens in the browser here (index.html embeds the AST and
runtime.js builds the DOM at load). Plan-DisplayModel.md Phase 3 moves that to a
build-time HTML emitter in this module; Phase 2 is the module split only.
"""
from __future__ import annotations

import argparse
import html
import os
import re
import sys
from typing import Optional

from .. import ast as lmrast
from . import html as render_html
from ..parser import (
    Deck, LemurError, Parser, deck_to_ast, iter_blocks, load_lines,
)

# --------------------------------------------------------------------------
# renderer assets + external dependencies
# --------------------------------------------------------------------------

# the renderer assets (runtime.js, base.css, tokens.css, shell.html, themes,
# fonts) ship inside the package at lemur/assets/, so an installed package is
# self-contained. This file is lemur/emit/slides.py, so two dirnames up is the
# package root (lemur/).
ASSETS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets")
# MathJax 4 dropped the 'es5/' directory and the '-full' bundles: the combined
# SVG component is 'tex-svg.js' at the package root. '{{mathjax}}' in the
# template is the full script url (CDN here, or the vendored path under
# '--assets'). The tex 'html' extension ('\class', needed for the mark wrappers
# the bridge injects) is autoloaded by this component.
MATHJAX_CDN = "https://cdn.jsdelivr.net/npm/mathjax@4/tex-svg.js"
MATHJAX_LOCAL = "mathjax/tex-svg.js"     # vendored copy (see copy_mathjax)
# highlight.js (common bundle) for code colorization; loaded only when a deck
# has code blocks (item 6). CDN even under --assets (which vendors MathJax).
HLJS_CDN = "https://cdn.jsdelivr.net/npm/@highlightjs/cdn-assets@11/highlight.min.js"

# the human description of a theme is the first css comment in theme.css
RE_THEME_DESC = re.compile(r"/\*\s*(.*?)\s*\*/", re.S)


def _read(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return fh.read()
    except OSError as exc:
        raise LemurError(f"cannot read renderer asset: {exc}", path, 0) from exc


def _write(path: str, text: str) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def render_template(tmpl: str, mapping: dict) -> str:
    """Render a lemur html template.

    Two constructs, deliberately nothing more:
        {{key}}                substituted with mapping[key]
        {{?key}} ... {{/key}}  included iff mapping[key] is non-empty
    Conditionals may nest across *different* keys (resolved iteratively);
    nesting the same key inside itself is unsupported. Conditionals are
    resolved before substitution, so placeholders inside a dropped block
    vanish with it, and substituted user content is never re-scanned (no
    template injection from slide content). Unknown placeholders are left
    verbatim with a warning, since '{{word}}' can legitimately occur in a
    template author's javascript.
    """
    cond = re.compile(r"\{\{\?(\w+)\}\}(.*?)\{\{/\1\}\}", re.S)
    prev = None
    while prev != tmpl:
        prev = tmpl
        tmpl = cond.sub(
            lambda m: m.group(2) if mapping.get(m.group(1)) else "", tmpl)

    def sub(m: re.Match) -> str:
        key = m.group(1)
        if key not in mapping:
            print(f"lemur: warning: unknown template placeholder "
                  f"'{{{{{key}}}}}' left as-is", file=sys.stderr)
            return m.group(0)
        return str(mapping[key])

    return re.sub(r"\{\{(\w+)\}\}", sub, tmpl)


# --------------------------------------------------------------------------
# themes (Plan.md Section 6): a theme is a directory 'themes/<name>/' holding
# theme.css (tokens). The build concatenates lemur/assets/base.css + the theme's
# theme.css into the output's slides.css. Keeping structure in base.css and
# tokens in theme.css avoids the per-template css duplication of old templates.
# --------------------------------------------------------------------------


def theme_search_path(doc_dir: Optional[str] = None,
                      extra_dir: Optional[str] = None) -> list[str]:
    """Directories that may hold theme folders, in priority order: an explicit
    '--theme-dir', the $LEMUR_THEMES environment variable (os.pathsep-
    separated), 'themes/' next to the document (a deck can ship and shadow its
    own theme), and the built-in 'lemur/assets/themes/' (the shipped ones).
    Non-existing directories are skipped by the callers."""
    dirs: list[str] = []
    if extra_dir:
        dirs.append(extra_dir)
    env = os.environ.get("LEMUR_THEMES", "")
    dirs.extend(d for d in env.split(os.pathsep) if d)
    if doc_dir:
        dirs.append(os.path.join(doc_dir, "themes"))
    dirs.append(os.path.join(ASSETS_DIR, "themes"))
    seen, out = set(), []
    for d in dirs:
        ad = os.path.abspath(d)
        if ad not in seen:
            seen.add(ad)
            out.append(d)
    return out


def find_theme(name: str, doc_dir: Optional[str] = None,
               extra_dir: Optional[str] = None) -> str:
    """Resolve a theme name to its directory (which must contain theme.css).
    A name containing a path separator is treated as a direct path to a theme
    directory; a bare name is looked up along the theme search path."""
    if os.sep in name or "/" in name:
        if os.path.isdir(name) and \
                os.path.exists(os.path.join(name, "theme.css")):
            return name
        raise LemurError(
            f"theme directory not found (needs theme.css): {name}")
    dirs = theme_search_path(doc_dir, extra_dir)
    for d in dirs:
        cand = os.path.join(d, name)
        if os.path.exists(os.path.join(cand, "theme.css")):
            return cand
    raise LemurError(
        f"theme '{name}' not found; searched for '{name}/theme.css' in: "
        + ", ".join(dirs))


def theme_desc(theme_dir: str) -> str:
    """The theme's one-line description: the first css comment in theme.css."""
    try:
        head = _read(os.path.join(theme_dir, "theme.css"))[:400]
    except LemurError:
        return "(unreadable)"
    m = RE_THEME_DESC.search(head)
    # the first line of the first css comment (multi-line comments describe the
    # customization options and should not leak into the one-line description)
    return " ".join(m.group(1).splitlines()[0].split()) if m else ""


def list_themes(doc_dir: Optional[str] = None,
                extra_dir: Optional[str] = None) -> list[tuple]:
    """Collect available themes as (name, dir, desc). Earlier search
    directories shadow later ones, mirroring find_theme's resolution."""
    seen: set = set()
    found: list[tuple] = []
    for d in theme_search_path(doc_dir, extra_dir):
        if not os.path.isdir(d):
            continue
        for name in sorted(os.listdir(d)):
            cand = os.path.join(d, name)
            if not os.path.exists(os.path.join(cand, "theme.css")):
                continue
            if name in seen:
                continue
            seen.add(name)
            found.append((name, cand, theme_desc(cand)))
    return found


def load_theme(name: str, doc_dir: Optional[str] = None,
               extra_dir: Optional[str] = None) -> str:
    """Resolve a theme and return its slides.css, concatenated in cascade order:
    the design tokens (lemur/assets/tokens.css, the theming surface), then the
    structure (lemur/assets/base.css), then the theme's overrides (theme.css). A
    restyle edits tokens, never the structural selectors (Plan-DisplayModel §3)."""
    theme_dir = find_theme(name, doc_dir, extra_dir)
    return "\n".join((
        _read(os.path.join(ASSETS_DIR, "tokens.css")),
        _read(os.path.join(ASSETS_DIR, "base.css")),
        _read(os.path.join(theme_dir, "theme.css")),
    ))


def resolve_theme_name(meta: dict, cli_theme: Optional[str]) -> str:
    """Theme precedence: CLI '--theme' > '!theme' > the 'clean' default."""
    return cli_theme or meta.get("theme") or "clean"


def deck_dimensions(meta: dict) -> tuple[int, int]:
    """Design box for the aspect (Full HD default, 4:3 otherwise)."""
    if meta.get("aspect") == "4:3":
        return 1440, 1080
    return 1920, 1080


# --------------------------------------------------------------------------
# build: parse (or load) a document and write the output folder
# --------------------------------------------------------------------------


def _prepare(path: str, theme: Optional[str], theme_dir: Optional[str]):
    """Shared front end of build: parse and resolve the theme.
    Returns (deck, slides_css, theme_name)."""
    lines = load_lines(path)
    deck = Parser(lines).parse()
    if not deck.groups and not deck.meta.get("title"):
        raise LemurError("document contains no slides", path, 0)
    doc_dir = os.path.dirname(os.path.abspath(path))
    name = resolve_theme_name(deck.meta, theme)
    css = load_theme(name, doc_dir, theme_dir)
    return deck, css, name


def _iter_img_srcs(deck: Deck):
    for group in deck.groups:
        for slide in group:
            for b in iter_blocks(slide.blocks):
                if b.kind == "image":
                    yield from b.data["srcs"]
    for key in ("titleimage", "logo"):
        if deck.meta.get(key):
            yield deck.meta[key]


def copy_figures(deck: Deck, doc_dir: str, outdir: str) -> None:
    """Copy every figure referenced by a relative path into the output folder,
    preserving its relative location so the emitted '<img src>' still resolves.
    URLs and absolute paths are left untouched."""
    import shutil
    for src in _iter_img_srcs(deck):
        if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", src) or \
                os.path.isabs(src):
            continue
        src_path = os.path.join(doc_dir, src)
        if not os.path.exists(src_path):
            print(f"lemur: warning: figure not found, not copied: {src_path}",
                  file=sys.stderr)
            continue
        dst_path = os.path.join(outdir, src)
        os.makedirs(os.path.dirname(dst_path) or ".", exist_ok=True)
        shutil.copy2(src_path, dst_path)


def copy_mathjax(assets: str, outdir: str) -> None:
    """Vendor MathJax for an offline deck. 'assets' is a directory containing a
    'mathjax' package with 'tex-svg.js' at its root (the MathJax 4 layout, e.g.
    after 'npm install mathjax@4' in it); it is copied to '<outdir>/mathjax', and
    the template's '{{mathjax}}' points at 'mathjax/tex-svg.js'. MathJax resolves
    its fonts and sub-components relative to the loaded script, so the vendored
    copy works with no further configuration."""
    import shutil
    src = os.path.join(assets, "mathjax")
    if not os.path.isfile(os.path.join(src, "tex-svg.js")):
        raise LemurError(
            f"--assets: MathJax not found at {src}; run 'npm install mathjax@4' "
            f"in {assets} (expects {os.path.join('mathjax', 'tex-svg.js')})")
    dst = os.path.join(outdir, "mathjax")
    if os.path.isdir(dst):
        shutil.rmtree(dst)
    shutil.copytree(src, dst)


def copy_fonts(outdir: str) -> None:
    """Copy the vendored OFL fonts into '<outdir>/fonts/'. The deck lays out in a
    fixed design box and scales it uniformly, so its layout is only reproducible
    if the font metrics are identical everywhere; shipping the fonts (used ahead
    of any system font, declared as '@font-face' in base.css) makes a slide wrap
    and size the same on every machine and browser. Ships the woff2 plus their
    licenses (SIL OFL); see lemur/assets/fonts/README.md."""
    import shutil
    src = os.path.join(ASSETS_DIR, "fonts")
    dst = os.path.join(outdir, "fonts")
    os.makedirs(dst, exist_ok=True)
    for fn in os.listdir(src):
        if fn.endswith(".woff2") or fn.startswith("OFL-"):
            shutil.copy2(os.path.join(src, fn), os.path.join(dst, fn))


def build(path: str, outdir: str, theme: Optional[str] = None,
          theme_dir: Optional[str] = None, assets: Optional[str] = None,
          print_mode: bool = False) -> str:
    """Compile a master .lmr into a self-contained folder: index.html (the deck
    DOM, rendered from the neutral AST by render_html), slides.css (the theme),
    runtime.js, the bundled fonts, and copied figures. With 'assets', MathJax is
    vendored too; otherwise it loads from the CDN. With 'print_mode', the deck
    builds its frozen print pages eagerly on load."""
    deck, css, _name = _prepare(path, theme, theme_dir)
    ast = deck_to_ast(deck)
    rendered = render_html.render_deck(ast)          # AST -> slide DOM (HTML)
    shell = _read(os.path.join(ASSETS_DIR, "shell.html"))
    meta = deck.meta
    has_code = any(b.kind == "code"
                   for g in deck.groups for s in g
                   for b in iter_blocks(s.blocks))
    code_assets = (f'<script defer src="{HLJS_CDN}"></script>'
                   if has_code else "")
    mapping = {
        "doc_title": html.escape(meta.get("title", "Lecture")),
        "width": rendered.design_w, "height": rendered.design_h,
        "mathjax": MATHJAX_LOCAL if assets else MATHJAX_CDN,
        "code_assets": code_assets,
        "deck_print": ' data-print="eager"' if print_mode else "",
        "deck_attrs": rendered.attrs,
        "deck_html": rendered.html,
    }
    html_doc = render_template(shell, mapping)

    os.makedirs(outdir, exist_ok=True)
    _write(os.path.join(outdir, "index.html"), html_doc)
    _write(os.path.join(outdir, "slides.css"), css)
    _write(os.path.join(outdir, "runtime.js"),
           _read(os.path.join(ASSETS_DIR, "runtime.js")))

    copy_fonts(outdir)                 # deterministic cross-machine layout
    doc_dir = os.path.dirname(os.path.abspath(path))
    copy_figures(deck, doc_dir, outdir)
    if assets:
        copy_mathjax(assets, outdir)
    return outdir


# --------------------------------------------------------------------------
# cli
# --------------------------------------------------------------------------


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="compile a lemur (.lmr) document into a self-contained "
                    "HTML slide-deck folder")
    ap.add_argument("input", nargs="?", help="master .lmr file")
    ap.add_argument("-o", "--output", metavar="DIR",
                    help="output directory (default: the input file's stem)")
    ap.add_argument("--theme", default=None, metavar="NAME_OR_DIR",
                    help="theme name (searched along the theme path) or path "
                    "to a theme directory; overrides the document's '!theme'")
    ap.add_argument("--theme-dir", default=None, metavar="DIR",
                    help="prepend DIR to the theme search path (also: "
                    "$LEMUR_THEMES, 'themes/' next to the document, "
                    "and the built-in 'lemur/assets/themes/')")
    ap.add_argument("--assets", default=None, metavar="DIR",
                    help="vendor MathJax from DIR (expects DIR/mathjax/tex-svg.js, "
                    "e.g. after 'npm install mathjax@4') for an offline deck "
                    "instead of the CDN")
    ap.add_argument("--print", dest="print_mode", action="store_true",
                    help="build the frozen per-step print pages eagerly on "
                    "load, so 'chrome --headless --print-to-pdf' produces a "
                    "handout PDF (one page per cumulative step) with no extra "
                    "tooling; without it, Ctrl-P builds them on demand")
    ap.add_argument("--list-themes", action="store_true",
                    help="list themes found on the search path and exit")
    args = ap.parse_args(argv)

    if args.list_themes:
        doc_dir = (os.path.dirname(os.path.abspath(args.input))
                   if args.input else os.getcwd())
        found = list_themes(doc_dir, args.theme_dir)
        if not found:
            print("lemur: no themes found; searched: "
                  + ", ".join(theme_search_path(doc_dir, args.theme_dir)),
                  file=sys.stderr)
            return 1
        width = max(len(n) for n, _, _ in found)
        for name, path, desc in found:
            print(f"{name:{width}s}  {desc}  [{path}]")
        return 0

    if not args.input:
        ap.error("input file required (or use --list-themes)")

    outdir = args.output or re.sub(r"\.lmr$", "",
                                   os.path.basename(args.input)) or "deck"
    try:
        build(args.input, outdir, args.theme, args.theme_dir, args.assets,
              args.print_mode)
    except LemurError as exc:
        print(f"lemur: error: {exc}", file=sys.stderr)
        return 1
    print(f"lmr2slides: wrote {outdir}/ "
          "(index.html, slides.css, runtime.js, fonts, figures)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
