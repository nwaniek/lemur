"""lmrast — the shared lemur AST contract.

The neutral document AST (spec/ast.schema.json) is the single interface between
the parser (lemur.parser) and the emitters (lemur.emit.slides -> a self-contained HTML
deck, lmr2tex.py -> LaTeX). This module holds what all of them must agree on: the
contract version, the vocabulary of node types, and helpers to load / validate /
serialize an AST document.

It is stdlib-only and imports neither the parser nor any emitter, so the
dependency always points inward: lmrast <- lemur, lmrast <- lmr2slides,
lmrast <- lmr2tex. See Plan-DisplayModel.md.
"""
from __future__ import annotations

import json

# Contract version. Bumped only on a breaking AST change; an emitter refuses a
# version it does not understand rather than mis-rendering it. Single source of
# truth for the `astVersion` field the parser writes and the emitters check.
AST_VERSION = 1

# The node-type vocabulary (mirrors spec/ast.schema.json). Emitters dispatch on
# node["type"]; these sets let an emitter assert it covers the whole contract and
# catch a newly added node type that was never wired up. `code`/`math` appear in
# both because they exist as block and inline forms.
BLOCK_TYPES = frozenset({
    "pagebreak", "heading", "para", "list", "code", "math", "table", "figure",
    "columns", "stack", "env", "style", "annotate", "connect", "spacer",
    "notes", "bibliography", "embed", "anim", "plot", "shader", "compute",
})
INLINE_TYPES = frozenset({
    "text", "strong", "emph", "strike", "underline", "code", "math", "link",
    "xref", "cite", "mark", "span", "break",
})


class ASTError(ValueError):
    """An AST document is malformed or of an unsupported contract version."""


def check(ast: dict) -> dict:
    """Validate an AST document's top-level shape and version; return it as-is.

    A light structural + version gate (not full JSON-Schema validation, which
    would pull in a non-stdlib dependency) — enough for an emitter to refuse the
    wrong version cleanly rather than mis-render it. The schema is the full spec;
    tests validate example decks against it."""
    if not isinstance(ast, dict):
        raise ASTError("AST root must be a JSON object")
    version = ast.get("astVersion")
    if version != AST_VERSION:
        raise ASTError(
            f"unsupported astVersion {version!r}; this tool speaks {AST_VERSION}")
    for key in ("meta", "body"):
        if key not in ast:
            raise ASTError(f"AST is missing the required {key!r} field")
    return ast


def loads(text: str) -> dict:
    """Parse and validate an AST from a JSON string."""
    return check(json.loads(text))


def load(source) -> dict:
    """Load and validate an AST from a filesystem path or an open text stream."""
    if hasattr(source, "read"):
        return check(json.load(source))
    with open(source, encoding="utf-8") as fh:
        return check(json.load(fh))


def dumps(ast: dict, *, indent: int = 2) -> str:
    """Serialize an AST to canonical, human-readable JSON (the `--ast` output and
    what the emitters consume). Emitters add any target-specific escaping on top
    (e.g. lmr2slides makes it `<script>`-safe when embedding)."""
    return json.dumps(ast, indent=indent)
