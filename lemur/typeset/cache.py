"""On-disk cache for expensive typesetting results (LaTeX runs).

Keyed on a content hash, so identical maths never recompiles — which is what
makes a rebuild (and a future ``--watch`` loop) fast. Set ``LEMUR_CACHE`` to
override the location; otherwise ``$XDG_CACHE_HOME/lemur``.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path


def cache_dir() -> Path:
    env = os.environ.get("LEMUR_CACHE")
    if env:
        d = Path(env)
    else:
        base = os.environ.get("XDG_CACHE_HOME") or (Path.home() / ".cache")
        d = Path(base) / "lemur"
    d.mkdir(parents=True, exist_ok=True)
    return d


def key_for(*parts: str) -> str:
    h = hashlib.sha256()
    for p in parts:
        h.update(p.encode("utf-8"))
        h.update(b"\0")
    return h.hexdigest()[:32]


def get(namespace: str, key: str, suffix: str = ".svg") -> str | None:
    p = cache_dir() / namespace / f"{key}{suffix}"
    try:
        return p.read_text(encoding="utf-8")
    except OSError:
        return None


def put(namespace: str, key: str, value: str, suffix: str = ".svg") -> None:
    d = cache_dir() / namespace
    d.mkdir(parents=True, exist_ok=True)
    tmp = d / f".{key}.tmp"
    tmp.write_text(value, encoding="utf-8")
    tmp.replace(d / f"{key}{suffix}")
