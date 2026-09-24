"""Step gates — *when* something is visible, as a set of build-step intervals.

A reveal spec (``spec/ast.schema.json#/$defs/reveal``) is a comma-separated list
of terms: ``n`` (only step n), ``n-`` (from n on), ``-n`` (up to n) or ``n-m``
(n through m). A **gate** is its normalised form: a sorted tuple of disjoint
``(appear, until)`` intervals, ``until=None`` meaning "open-ended".

    ALWAYS = ((0, None),)          # the default: visible on every step
    NEVER  = ()                    # an empty intersection: laid out, never shown

Gates compose by intersection (:func:`combine`) — a `+` item inside a `!when`
block inside a `!stack` layer is visible only where all three agree. Hidden
content still takes its space (like CSS ``visibility: hidden``), so revealing it
never reflows the slide.
"""

from __future__ import annotations

import re

__all__ = ["ALWAYS", "NEVER", "parse_spec", "gate_of", "combine", "normalize",
           "is_always", "first_step", "max_step", "from_range"]

ALWAYS: tuple = ((0, None),)
NEVER: tuple = ()

_TERM = re.compile(r"(\d*)(-?)(\d*)")


def normalize(intervals) -> tuple:
    """Sort and merge overlapping/adjacent intervals."""
    ivs = sorted(((int(a), None if u is None else int(u)) for a, u in intervals
                  if u is None or int(u) >= int(a)), key=lambda iv: iv[0])
    out: list = []
    for a, u in ivs:
        if out:
            pa, pu = out[-1]
            if pu is None or a <= pu + 1:          # overlaps or touches the previous
                out[-1] = (pa, None if (pu is None or u is None) else max(pu, u))
                continue
        out.append((a, u))
    return tuple(out)


def parse_spec(spec) -> tuple:
    """A reveal spec string → a gate. Unparseable terms are ignored; a spec with
    no usable term means *always* (never silently hide content)."""
    ivs = []
    for term in str(spec or "").split(","):
        term = term.strip()
        m = _TERM.fullmatch(term)
        if not term or not m:
            continue
        a, dash, b = m.groups()
        if not dash:
            if a:
                ivs.append((int(a), int(a)))
        elif a or b:
            ivs.append((int(a) if a else 0, int(b) if b else None))
    return normalize(ivs) if ivs else ALWAYS


def gate_of(node) -> tuple:
    """The gate of an AST node's ``reveal`` (``ALWAYS`` if it has none)."""
    rev = node.get("reveal") if isinstance(node, dict) else None
    if not rev:
        return ALWAYS
    return parse_spec(rev.get("spec", ""))


def from_range(appear: int = 0, until: "int | None" = None) -> tuple:
    """The legacy ``(appear, until)`` pair as a gate."""
    return normalize([(appear, until)])


def combine(*gates) -> tuple:
    """Intersect gates (visible only where all of them are)."""
    out = ALWAYS
    for g in gates:
        if g is None or g == ALWAYS:
            continue
        acc = []
        for a1, u1 in out:
            for a2, u2 in g:
                a = max(a1, a2)
                u = u2 if u1 is None else (u1 if u2 is None else min(u1, u2))
                if u is None or u >= a:
                    acc.append((a, u))
        out = normalize(acc)
    return out


def is_always(g) -> bool:
    return g == ALWAYS or (len(g) == 1 and g[0][0] <= 0 and g[0][1] is None)


def first_step(g) -> int:
    """The first step on which the gate is open (0 for always / never)."""
    return g[0][0] if g else 0


def max_step(g) -> int:
    """The largest step number a gate references (for counting a slide's steps,
    as the HTML runtime did: the largest number used anywhere)."""
    m = 0
    for a, u in g:
        m = max(m, a, u or 0)
    return m
