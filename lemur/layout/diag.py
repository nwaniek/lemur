"""Build diagnostics for the layout/emit stages.

Layout code reports problems here (a LaTeX error, a missing image, content
overflowing its slide) instead of aborting the whole build or failing silently;
the emitter prints them with the slide they belong to. ``muted()`` suppresses
reports while content is only being *measured* (a dry-run layout), so every
problem is reported once.
"""

from __future__ import annotations

import contextlib

__all__ = ["warn", "drain", "muted"]

_items: list = []
_mute = 0


def warn(msg: str) -> None:
    if not _mute and msg not in _items:
        _items.append(msg)


def drain() -> list:
    out = list(_items)
    _items.clear()
    return out


@contextlib.contextmanager
def muted():
    global _mute
    _mute += 1
    try:
        yield
    finally:
        _mute -= 1
