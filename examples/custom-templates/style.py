"""The smallest custom template, in one file. `lmr2svg` auto-loads this because
it sits next to deck.lmr; a slide selects the template with `!slide[.banner]`."""

from lemur.style import Style, Region, register, line, flow


class Style(Style):
    # near-default design; just a slightly wider body region for the banner
    body_region = Region(140, 420, 1640, 560)


@register("banner")
def banner(ctx):
    """A full-width accent band with the title reversed out, body below."""
    d = ctx.design
    ctx.slide.add_rect(0, 0, d.width, 300, d.accent)          # top band
    region = (140.0, d.width - 280.0)
    line(ctx, ctx.title, 88.0, 96.0, region, "#ffffff", weight=700)
    flow(ctx, ctx.blocks, region, 420.0)                     # body below the band
