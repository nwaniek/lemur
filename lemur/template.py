"""Custom slide templates (compatibility re-export).

A template is a plain ``render(ctx)`` function registered with :func:`register`;
lemur ships ``cover``, ``section``, and ``content``, and you can add your own. The
canonical home for a deck's templates (and its design) is a single ``style.py``
next to the ``.lmr`` — see :mod:`lemur.style`, which is what new decks import.
This module simply re-exports the same names for convenience/back-compat::

    from lemur.style import register, flow, footer

    @register("content")
    def content(ctx):
        ...

See :mod:`lemur.style` for the full API (helpers, ``Ctx`` fields, composition).
"""

from .emit.svg import (  # noqa: F401
    Ctx, body_bottom, content, cover, flow, footer, header, line, logo, region,
    register, section,
)

__all__ = ["register", "Ctx", "line", "flow", "footer", "header", "logo",
           "region", "body_bottom", "content", "cover", "section"]
