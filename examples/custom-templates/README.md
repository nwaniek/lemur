# Writing a custom template

The smallest possible custom template, to show the whole path end to end. Design
and templates live in **one `style.py`** next to the deck; `lmr2svg` auto-loads
it. A slide opts into the template with `!slide[.banner]`.

## Build

```sh
python3 lmr2svg.py examples/custom-templates/deck.lmr -o custom.html
```

## style.py

```python
from lemur.style import Style, Region, register, line, flow

class Style(Style):                                        # near-default design
    body_region = Region(140, 420, 1640, 560)

@register("banner")
def banner(ctx):
    d = ctx.design
    ctx.slide.add_rect(0, 0, d.width, 300, d.accent)       # a full-width band
    region = (140.0, d.width - 280.0)
    line(ctx, ctx.title, 88.0, 96.0, region, "#ffffff", weight=700)
    flow(ctx, ctx.blocks, region, 420.0)                   # body below the band
```

`class Style` is optional — omit it and the template rides on the theme/default
palette. Selection order (`_template_for`): a `!slide[.name]` whose name is a
registered template wins; otherwise the slide's role (`cover`/`section`/
`content`); otherwise `content`. Names that are *not* registered templates
(`center`, `middle`, `plain`, `dark`) are treated as **layout modifiers**
instead — see `../transitions/`.

The module runs at build time as trusted code. Put it next to your `.lmr` files,
or share one from "corporate."
