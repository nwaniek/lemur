from lemur.style import Style, Region, register, line, flow, footer


class Style(Style):
    body_region = Region(140, 420, 1640, 560)


@register("banner")
def banner(ctx):
    d = ctx.design
    ctx.slide.add_rect(0, 0, d.width, 300, d.accent)          # a full-width band
    region = (140.0, d.width - 280.0)
    line(ctx, ctx.title, 88.0, 96.0, region, "#ffffff", weight=700)
    flow(ctx, ctx.blocks, region, 420.0)                      # the body below it
    footer(ctx)
