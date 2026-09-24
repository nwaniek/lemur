# Corporate identity

A branded deck whose entire design lives in **one `style.py`** next to the deck —
`lmr2svg` loads it automatically. `style.py` holds both halves of the mechanism:

- a **`class Style`** — the design box (brand palette, sizes, the `region`s placed
  below the brand bar, a default `transition`), subclassing the base `Style`
  (override just the fields you need);
- the **templates** — plain `render(ctx)` functions: it re-registers the built-in
  `content` and `cover` names, so *every* regular slide gets the full-width navy
  brand bar + logo, and the cover is full-bleed navy.

## Build

```sh
python3 lmr2svg.py examples/corporate/deck.lmr -o corporate.html
```

No flags: the deck's folder has `style.py`, so it is picked up. (Use
`--style <path>` to point elsewhere.)

## How it works

```python
from lemur.style import Style, Region, register, line, logo, flow, footer, body_bottom

class Style(Style):                          # start from clean, override a few fields
    title = "#1b3a6b"
    accent = "#c8a24a"
    title_size = 60
    body_region = Region(80, 320, 1760, 610)
    transition = ("push", "rise")

@register("content")                         # restyle every regular slide
def content(ctx):
    d = ctx.design
    ctx.slide.add_rect(0, 0, d.width, 150, "#1b3a6b")     # brand bar
    logo(ctx)                                             # !logo, top-right
    ...
    flow(ctx, ctx.blocks, ..., rbottom=body_bottom(ctx))
    footer(ctx)                                           # !footer + number
```

A template is a plain `render(ctx)` function: it draws onto `ctx.slide` and leans
on the free helpers (`line`, `flow`, `logo`, `footer`, `header`, `region`,
`body_bottom`), reading the resolved design off `ctx.design`. `ctx` also carries
`title`, `blocks`, `meta`, `pres` (deck chrome), `mods` (variant modifiers),
`number`, `total`, and the once-resolved `serif`/`mono`/`text_style`.

Registrations are isolated per build, so a `style.py` that replaces `content`
never affects another deck. To *extend* a built-in rather than replace it, compose
— call `content(ctx)` then add your own drawing. To brand only *some* slides,
register a new name and select it per slide with `!slide[.name]` (see
`../custom-templates/`).
