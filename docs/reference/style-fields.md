# Style fields

The fields of a design, set as class attributes of `Style` in a
[`style.py`](../design/style.md). The defaults are those of the `clean` theme.
Sizes and coordinates are pixels in the design box.

## Design box

| Field | Default | |
|---|---|---|
| `width` | `1920` | design box width |
| `height` | `1080` | design box height (`!aspect 4:3` makes the box 1440 wide) |

## Colours

| Field | Default | |
|---|---|---|
| `bg` | `#ffffff` | the slide background |
| `title` | `#232629` | slide titles |
| `body` | `#232629` | running text (and the default colour of animation shapes) |
| `math` | `#232629` | maths |
| `caption` | `#666666` | captions, footer and other muted text |
| `accent` | `#2e5e6e` | the accent: title rule, links, section titles, `.accent` |
| `rule` | `#d5d8db` | thin rules (footer line, table rules) |

## Code

| Field | Default | |
|---|---|---|
| `code` | `#232629` | code text |
| `code_bg` | `#f2f2f2` | the code panel and inline-code background |
| `code_keyword` | `#a3562a` | keywords |
| `code_string` | `#3a7d44` | strings |
| `code_number` | `#7a4b94` | numbers |
| `code_comment` | `#8a9099` | comments |
| `code_function` | `#2e5e6e` | function names |
| `code_type` | `#2e6e5e` | types and classes |
| `code_highlight` | `#f0c828` | the background of highlighted lines |

## Fonts

| Field | Default | |
|---|---|---|
| `serif` | `("Source Sans 3", "DejaVu Sans", "sans-serif")` | the text face: family names, tried in order (the name is historical; any face works) |
| `mono` | `("JetBrains Mono", "DejaVu Sans Mono", "monospace")` | the code face |

A tuple or a comma-separated string. The fonts must be installed where the deck
is built. The shipped faces (Source Sans 3, Source Serif 4, JetBrains Mono,
Libre Baskerville) come with lemur.

## Sizes

| Field | Default | |
|---|---|---|
| `title_size` | `54` | slide titles |
| `body_size` | `40` | running text; `em`-based sizes are relative to it |
| `math_size` | `40` | maths |
| `code_size` | `25` | code |
| `table_size` | `34` | tables |
| `caption_size` | `28` | captions |
| `line_height` | `1.45` | line spacing of running text, as a multiple of the size |
| `title_weight` | `650` | the weight of titles (100–900) |
| `title_spacing` | `-0.01` | letter spacing of titles, in em |
| `title_rule` | `3` | the height of the accent rule under titles (0: none) |

## Title slide

| Field | Default | |
|---|---|---|
| `cover_title_scale` | `1.7` | the title size on the title slide, in body ems |
| `cover_rule` | `False` | a short accent rule between subtitle and byline |
| `cover_caps` | `False` | a small, letter-spaced, upper-case byline |

## Regions

| Field | Default | |
|---|---|---|
| `title_region` | `Region(96, 72, 1728, None)` | where titles go |
| `body_region` | `Region(96, 150, 1728, 858)` | where content goes; its `y` is the earliest the body may start below the title |

`Region(x, y, w, h)`; `h=None` means "as tall as the content". Check regions
with `lmr2svg deck.lmr --wireframe`.

## Behaviour

| Field | Default | |
|---|---|---|
| `transition` | `None` | the default transition as `(across, step)`, e.g. `("push", "rise")`; a deck's `!transition` overrides it |
| `preamble` | `None` | a LaTeX preamble file, relative to the `style.py`; replaces the default preamble for maths |
