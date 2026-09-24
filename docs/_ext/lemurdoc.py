"""Sphinx support for the lemur documentation.

* A Pygments lexer for lemur, registered as ``lemur`` (and ``lmr``), so fenced
  blocks in the docs are highlighted.
* The ``lemur-example`` directive: a lemur snippet shown as highlighted source
  next to a **live preview** — the snippet is built with ``lmr2svg`` while the
  docs build, and the resulting self-contained deck is embedded in an iframe
  (click it, or focus it and use the arrow keys, to step through).

  ````md
  ```{lemur-example}
  :height: 360          (optional: preview height in px; default: 16:9)
  :theme: dark          (optional: a shipped theme)
  :step: 2              (optional: open at this step; "last" = fully built)
  :files: bars.py       (optional: files from docs/snippets/ built alongside)

  !slide Hello
  Some **lemur**.
  ```
  ````

  A snippet without any ``!slide``/``#`` line is built as one slide. Builds are
  cached by content, so an unchanged snippet is not rebuilt.
"""

from __future__ import annotations

import hashlib
import html
import os
import re
import shutil
import sys
import tempfile

from docutils import nodes
from docutils.parsers.rst import directives
from pygments.lexer import RegexLexer, bygroups, include
from pygments.token import (Comment, Keyword, Name, Number, Operator, Punctuation, String,
                            Generic, Text, Whitespace)
from sphinx.util import logging
from sphinx.util.docutils import SphinxDirective

log = logging.getLogger(__name__)

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SNIPPETS = os.path.join(ROOT, "docs", "snippets")
OUT = "_lemur"        # previews, under the HTML output directory


# -- the lexer -------------------------------------------------------------------

class LemurLexer(RegexLexer):
    """lemur (.lmr) — directives, headings, lists, code/maths blocks and the
    inline marks (emphasis, maths, refs, marks, spans, overlays)."""

    name = "lemur"
    aliases = ["lemur", "lmr"]
    filenames = ["*.lmr"]

    tokens = {
        "root": [
            (r"^[ \t]*%%.*\n", Comment.Single),
            (r"^([ \t]*)(::)([ \t]*)(math)?", bygroups(Whitespace, Keyword, Whitespace, Keyword.Type), "codehead"),
            (r"^([ \t]*)(#{1,3})(\[[^\]\n]*\])?([^\n]*)",
             bygroups(Whitespace, Generic.Heading, Name.Attribute, Generic.Heading)),
            (r"^([ \t]*)(\^[A-Za-z0-9_-]+:)", bygroups(Whitespace, Name.Label)),
            (r"^([ \t]*)(!include)\b", bygroups(Whitespace, Keyword.Namespace)),
            (r"^([ \t]*)(![A-Za-z]+)", bygroups(Whitespace, Keyword), "directive"),
            (r"^([ \t]*)([-+*]|\d+\.)(<[^>\n]*>)?(?=[ \t])",
             bygroups(Whitespace, Operator, Name.Decorator)),
            include("inline"),
            (r"\n", Whitespace),
        ],
        "directive": [
            (r"\[[^\]\n]*\]", Name.Attribute),
            (r"<[^>\n]*>", Name.Decorator),
            (r"\^[A-Za-z0-9_-]+", Name.Label),
            (r"\n", Whitespace, "#pop"),
            include("inline"),
        ],
        "codehead": [
            (r"\[[^\]\n]*\]", Name.Attribute),
            (r"\^[A-Za-z0-9_-]+", Name.Label),
            (r"[A-Za-z0-9_+-]+", Keyword.Type),
            (r"[ \t]+", Whitespace),
            (r"\n", Whitespace, "#pop"),
        ],
        "inline": [
            (r"\\.", String.Escape),
            (r"`[^`\n]+`", String.Backtick),
            (r"\$[^$\n]+\$", String),
            (r"\\mk\{[A-Za-z0-9_-]+\}", Name.Function),
            (r"\*\*[^*\n]+\*\*", Generic.Strong),
            (r"__[^_\n]+__", Generic.Emph),
            (r"~~[^~\n]+~~|\+\+[^+\n]+\+\+", Generic.Deleted),
            (r"(\])(\{[^}\n]*\})", bygroups(Punctuation, Name.Attribute)),
            (r"(\])(\^[A-Za-z0-9_-]+)", bygroups(Punctuation, Name.Label)),
            (r"(\])(<[^>\n]*>)", bygroups(Punctuation, Name.Decorator)),
            (r"(\])(@\([^)\n]*\)|@[A-Za-z0-9_-]+)", bygroups(Punctuation, Name.Tag)),
            (r"@\([^)\n]*\)|@[A-Za-z0-9_-]+", Name.Tag),
            (r"\^[A-Za-z0-9_-]+", Name.Label),
            (r"<https?://[^>\n]+>|<[^>@\s]+@[^>\s]+>", String.Other),
            (r"[#][0-9A-Fa-f]{3,8}\b", Number.Hex),
            (r"->|<->|<-|--(?=\s)", Operator),
            (r"[^\\`$*_~+\]@^<#\-\n]+", Text),
            (r".", Text),
        ],
    }


class LemurBlockLexer(LemurLexer):
    """The lemur lexer, with the bodies of ``::`` blocks handed to the lexer of
    their language (LaTeX for ``:: math``) instead of being read as lemur."""

    name = "lemur"
    aliases = ["lemur", "lmr"]

    _HEAD = re.compile(r"^([ \t]*)::[ \t]*([A-Za-z0-9_+-]*)")

    def get_tokens_unprocessed(self, text):
        from pygments.lexers import get_lexer_by_name
        from pygments.util import ClassNotFound

        lines = text.splitlines(keepends=True)
        pos, i, chunk, chunk_at = 0, 0, [], 0

        def flush():
            nonlocal chunk
            if chunk:
                for idx, tok, val in RegexLexer.get_tokens_unprocessed(self, "".join(chunk)):
                    yield chunk_at + idx, tok, val
                chunk = []

        while i < len(lines):
            line = lines[i]
            m = self._HEAD.match(line)
            if not m:
                if not chunk:
                    chunk_at = pos
                chunk.append(line)
                pos += len(line)
                i += 1
                continue
            yield from flush()
            for idx, tok, val in RegexLexer.get_tokens_unprocessed(self, line):
                yield pos + idx, tok, val
            pos += len(line)
            i += 1
            indent, lang = len(m.group(1).expandtabs(4)), m.group(2) or "text"
            body = []
            while i < len(lines) and (not lines[i].strip()
                                      or len(lines[i]) - len(lines[i].lstrip()) > 0
                                      and len(lines[i].expandtabs(4)) - len(lines[i].expandtabs(4).lstrip()) > indent):
                body.append(lines[i])
                i += 1
            while body and not body[-1].strip():         # trailing blank lines belong to lemur
                i -= 1
                body.pop()
            try:
                sub = get_lexer_by_name("latex" if lang == "math" else lang)
            except ClassNotFound:
                sub = None
            code = "".join(body)
            if sub is None:
                if code:
                    yield pos, String, code
            else:
                for idx, tok, val in sub.get_tokens_unprocessed(code):
                    yield pos + idx, tok, val
            pos += len(code)
        yield from flush()


# -- the live example ---------------------------------------------------------------

_SLIDE = re.compile(r"^[ \t]*(!slide\b|#)", re.M)


_META = re.compile(r"^[ \t]*(%%|!(title|subtitle|author|institute|date|theme|transition|aspect|"
                   r"titleimage|header|footer|slidenumbers|logo|progress)\b)")


def _as_slide(source: str) -> str:
    """A snippet without slides: its leading configuration stays configuration,
    the rest becomes one slide (a configuration-only snippet is just a cover)."""
    lines = source.split("\n")
    k = 0
    while k < len(lines) and (not lines[k].strip() or _META.match(lines[k])):
        k += 1
    if k == len(lines):
        return source
    return "\n".join(lines[:k] + ["!slide", ""] + lines[k:])


def _build(source: str, files: list, theme: "str | None", outdir: str) -> str:
    """Build ``source`` (+ snippet files) with lmr2svg into ``outdir``; returns the
    file name (content-addressed, so unchanged snippets are reused)."""
    h = hashlib.blake2b(digest_size=10)
    h.update(source.encode())
    h.update((theme or "").encode())
    for f in files:
        with open(os.path.join(SNIPPETS, f), "rb") as fh:
            h.update(f.encode() + b"\0" + fh.read())
    name = f"{h.hexdigest()}.html"
    target = os.path.join(outdir, name)
    if os.path.exists(target):
        return name
    if ROOT not in sys.path:
        sys.path.insert(0, ROOT)
    from lemur.emit import svg

    deck = source if _SLIDE.search(source) else _as_slide(source)
    if theme:
        deck = f"!theme {theme}\n" + deck
    with tempfile.TemporaryDirectory(prefix="lemurdoc-") as tmp:
        for f in files:
            shutil.copy(os.path.join(SNIPPETS, f), os.path.join(tmp, os.path.basename(f)))
        src = os.path.join(tmp, "deck.lmr")
        with open(src, "w", encoding="utf-8") as fh:
            fh.write(deck)
        os.makedirs(outdir, exist_ok=True)
        svg.build(src, target)
    for w in getattr(svg, "LAST_WARNINGS", []) or []:
        log.warning(f"lemur-example: {w}")
    return name


class LemurExample(SphinxDirective):
    has_content = True
    option_spec = {
        "height": directives.positive_int,
        "theme": directives.unchanged,
        "step": directives.unchanged,
        "files": directives.unchanged,
        "caption": directives.unchanged,
        "source": directives.flag,       # also show the snippet files' source
    }

    def run(self):
        source = "\n".join(self.content) + "\n"
        files = (self.options.get("files") or "").split()
        outdir = os.path.join(self.env.app.outdir, OUT)
        try:
            name = _build(source, files, self.options.get("theme"), outdir)
        except Exception as exc:                      # a broken snippet must fail loudly
            raise self.error(f"lemur-example failed to build: {exc}")
        for f in files:
            self.env.note_dependency(os.path.join(SNIPPETS, f))

        depth = self.env.docname.count("/")
        step = self.options.get("step", "0")
        step = "999" if step == "last" else step
        src = "../" * depth + f"{OUT}/{name}#/1/{html.escape(step)}"
        height = self.options.get("height")
        style = f' style="height:{height}px;aspect-ratio:auto"' if height else ""
        caption = self.options.get("caption")

        code = nodes.literal_block(source, source, language="lemur")
        code["classes"].append("lemur-example-source")
        blocks = [code]
        if "source" in self.options:
            for f in files:
                with open(os.path.join(SNIPPETS, f), encoding="utf-8") as fh:
                    text = fh.read()
                lang = {".py": "python", ".glsl": "glsl"}.get(os.path.splitext(f)[1], "text")
                lit = nodes.literal_block(text, text, language=lang)
                lit["classes"].append("lemur-example-file")
                blocks.append(nodes.rubric(text=os.path.basename(f)))
                blocks.append(lit)
        frame = nodes.raw(
            "",
            f'<div class="lemur-preview"><iframe src="{src}" loading="lazy" title="live preview"{style}>'
            f'</iframe><div class="lemur-preview-hint">live preview — click it or use ← → to step'
            f'{" · " + html.escape(caption) if caption else ""}</div></div>',
            format="html")
        box = nodes.container(classes=["lemur-example"])
        box += blocks
        box += frame
        return [box]


def setup(app):
    from sphinx.highlighting import lexers
    lexers["lemur"] = LemurBlockLexer()
    lexers["lmr"] = LemurBlockLexer()
    app.add_directive("lemur-example", LemurExample)
    return {"version": "1.0", "parallel_read_safe": True, "parallel_write_safe": True}
