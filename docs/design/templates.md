# Templates

A **template** decides how one kind of slide is drawn. It is a plain Python
function `render(ctx)`, registered under a name in a
[`style.py`](style.md). It draws onto the slide and then lets lemur flow the
slide's content into a region.

## A first template

```python
# style.py
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
```

A slide opts into it with its class:

```{lemur-example}
:files: banner/style.py

!slide[.banner] A banner slide

The title sits in a band drawn by the template; the body flows below it.

- as usual
- with lists, maths such as $e^{i\pi} = -1$, and everything else
```

## Which template draws a slide

1. If a class of the slide (`!slide[.name]`) names a registered template, that
   template draws it.
2. Otherwise, the slide's **role** decides: `cover` (the title slide), `section`
   (a `#` divider) or `content` (every other slide).

Registering one of the built-in names `content`, `cover` or `section`
therefore restyles *every* slide of that kind, which is how a corporate design
puts its brand bar on all slides. Classes that are not templates (`.center`,
`.plain`, `.dark`, …) still apply as layout modifiers, available to the template
as `ctx.mods`.

## What a template gets: `ctx`

| Attribute | |
|---|---|
| `ctx.slide` | the slide to draw on (see below) |
| `ctx.design` | the resolved design: every [style field](../reference/style-fields.md), e.g. `ctx.design.accent`, `ctx.design.body_region` |
| `ctx.title` | the slide title (`ctx.title_inline`: the same as inline nodes, with maths and emphasis) |
| `ctx.blocks` | the slide's content, ready for `flow` |
| `ctx.role` | `"cover"`, `"section"` or `"content"` |
| `ctx.mods` | the slide's layout classes, e.g. `{"center", "plain"}` |
| `ctx.meta` | the deck metadata: `title`, `subtitle`, `authors`, `affiliation`, `date` |
| `ctx.pres` | the deck chrome: `header`, `footer`, `logo`, `titleImage`, … |
| `ctx.number`, `ctx.total` | this slide's number and the number of numbered slides |
| `ctx.doc_dir` | the deck's folder, for loading files |

## Helpers

All helpers are importable from `lemur.style`:

| Helper | Does |
|---|---|
| `line(ctx, text, size, top, (x, w), color, weight="normal", align="left")` | set one (wrapping) line of text or inline nodes; returns its height |
| `flow(ctx, blocks, (x, w), top, align="left", rbottom=None, middle=None)` | lay out content blocks from `top` down; returns the bottom. Pass the region's bottom as `rbottom` so that `!gap[fill]` and `.middle` work |
| `header(ctx)`, `footer(ctx)`, `logo(ctx)` | the deck's header, footer (with slide number) and logo, drawn as in the built-in templates |
| `region(ctx, "title"\|"body")` | a design region as `(x, w, y, h)` |
| `body_bottom(ctx)` | the bottom of the body region |

Drawing directly on the slide:

| Method | Draws |
|---|---|
| `ctx.slide.add_rect(x, y, w, h, fill, rx=0, opacity=None, stroke=None)` | a rectangle behind the content |
| `ctx.slide.add_image(x, y, w, h, href)` | an image (a data URI or a path) |
| `ctx.slide.add_back(svg)`, `ctx.slide.add_overlay(svg)` | raw SVG behind / in front of the content |
| `ctx.slide.bg = "#…"` | the slide's background colour |

All coordinates are design-box pixels, with the origin at the top left.

## Building on the built-in templates

The built-in templates are importable too (`from lemur.style import content,
cover, section`). To add something to every content slide without redrawing it,
call the built-in and draw on top:

```python
from lemur.style import register, content

@register("content")
def content_with_stamp(ctx):
    content(ctx)
    ctx.slide.add_rect(ctx.design.width - 40, 0, 40, 40, ctx.design.accent)
```

## A complete corporate design

`examples/corporate/style.py` is a full brand identity in one file: a palette, a
navy bar with the deck title and logo on every slide, an accent-ruled title, a
full-bleed cover and a default transition.

```{lemur-example}
:files: brand/style.py

!title Quarterly Review
!subtitle Message Passing Division
!author R. Example
!institute Acme Research
!date Q3 2026

!slide Where we are

- the pipeline is in production
+ throughput doubled since Q2
+ latency is the next target
```
