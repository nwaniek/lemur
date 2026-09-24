"""Corporate identity, all in one file: the design box (`class Style`) and the
templates (`render(ctx)` functions). `lmr2svg examples/corporate/deck.lmr` picks
this up automatically because it sits next to the deck. Templates draw onto
`ctx.slide` and read the resolved design off `ctx.design`.
"""

from lemur.style import Style, Region, register, line, logo, flow, footer, body_bottom

BRAND = "#1b3a6b"      # the brand navy; the palette below carries the rest


class Style(Style):
    """The design box: brand palette, regions placed below the 150px brand bar
    the template draws, and a default transition. Fields not set here keep the
    `clean` defaults."""
    title = "#1b3a6b"
    body = "#2b3440"
    accent = "#c8a24a"
    caption = "#7a869a"
    rule = "#dfe4ea"
    code_bg = "#eef1f6"
    title_size = 60
    title_region = Region(80, 210, 1760, None)
    body_region = Region(80, 320, 1760, 610)
    transition = ("push", "rise")


@register("content")
def content(ctx):
    """A branded regular slide: a full-width navy bar with the deck title and
    logo, then the slide title (accent-ruled) and the body below it."""
    d, s = ctx.design, ctx.slide
    s.add_rect(0, 0, d.width, 150, BRAND)                        # brand bar
    line(ctx, (ctx.meta or {}).get("title", ""), 30.0, 54.0, (80.0, d.width - 520), "#ffffff")
    logo(ctx)                                                    # white logo, top-right on the bar
    tr, br = d.title_region, d.body_region
    h = line(ctx, ctx.title, d.title_size, tr.y, (tr.x, tr.w), d.title, weight=700)
    s.add_rect(tr.x, tr.y + h + 12, tr.w, 4.0, d.accent)         # accent rule under the title
    flow(ctx, ctx.blocks, (br.x, br.w), br.y,
         align=("center" if "center" in ctx.mods else "left"), rbottom=body_bottom(ctx))
    footer(ctx)


@register("cover")
def cover(ctx):
    """A full-bleed navy cover built from the deck metadata."""
    d = ctx.design
    ctx.slide.bg = BRAND                 # full-bleed navy — also fills the letterbox
    mm, full, y = ctx.meta or {}, (140.0, float(d.width - 280)), 360.0
    y += line(ctx, mm.get("title", ""), 96.0, y, full, "#ffffff", weight=700) + 28
    y += line(ctx, mm.get("subtitle", ""), 44.0, y, full, "#aebbd0") + 72
    logo(ctx)
    authors = ", ".join(mm.get("authors", []) or [])
    y += line(ctx, authors, 36.0, y, full, "#ffffff", weight=600) + 14
    extra = " · ".join(x for x in (mm.get("affiliation"), mm.get("date")) if x)
    line(ctx, extra, 30.0, y, full, "#aebbd0")
