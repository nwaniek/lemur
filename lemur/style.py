"""Public API for a deck's ``style.py`` — the whole design in one file.

Drop a ``style.py`` next to your ``.lmr`` and ``lmr2svg`` picks it up (or pass
``--style <path>``). It replaces the old text ``.master`` + a separate templates
module: the design box and the templates live together.

**Design** — a **class ``Style``**: subclass a shipped theme (or the base) and
override just the fields you want::

    from lemur.style import Style, Region
    from lemur.themes import journal

    class Style(journal.Style):          # start from `journal`, tweak a few fields
        accent = "#c8a24a"
        body_region = Region(80, 320, 1760, 610)
        transition = ("push", "rise")

**Templates** — a template is a plain **``render(ctx)`` function** registered with
:func:`register`. It draws onto ``ctx.slide`` with the free helpers (:func:`line`,
:func:`flow`, :func:`footer`, :func:`header`, :func:`logo`, :func:`region`,
:func:`body_bottom`), reading the resolved design off ``ctx.design``. Register a
built-in name (`content`/`cover`/`section`) to restyle every slide of that kind,
or a new name to select per slide with ``!slide[.name]``::

    from lemur.style import register, flow, footer, logo

    @register("content")
    def content(ctx):
        ctx.slide.add_rect(0, 0, ctx.design.width, 150, "#1b3a6b")
        logo(ctx)
        flow(ctx, ctx.blocks, (80.0, ctx.design.width - 160), 210.0)
        footer(ctx)

To extend a built-in, compose: call the built-in ``content(ctx)`` then add your
own drawing. The module runs at build time as trusted code; its registrations are
isolated per build. ``ctx`` carries ``slide``, ``design``, ``serif``/``mono``/
``text_style``, ``title``, ``blocks``, ``role``, ``meta``, ``pres``, ``mods``,
``number``, ``total``, ``doc_dir``.
"""

from .master import Design, Region, Style, resolve_design  # noqa: F401
from .emit.svg import (  # noqa: F401
    Ctx, body_bottom, content, cover, flow, footer, header, line, load_style,
    logo, region, register, section,
)

__all__ = [
    "Style", "Region", "Design", "resolve_design",              # design
    "register", "Ctx", "load_style",                            # template registry
    "line", "flow", "footer", "header", "logo", "region", "body_bottom",  # helpers
    "content", "cover", "section",                              # built-in templates (for composition)
]
