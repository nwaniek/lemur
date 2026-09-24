# `style.py`: the design in one file

A deck's whole design (colours, fonts, sizes, layout, transitions, the LaTeX
preamble and custom slide templates) can live in one Python file, `style.py`,
next to the `.lmr` file. `lmr2svg` picks it up automatically, or you can point
to one with `--style path/to/style.py`.

## A class with fields

The design is a class named `Style`. Subclass a shipped theme and override only
the fields you want to change:

```python
# style.py
from lemur.style import Style, Region
from lemur.themes import journal


class Style(journal.Style):          # start from `journal`, change a few fields
    accent = "#c0661f"
    title = "#5b2a0e"
    title_size = 60
    body_region = Region(96, 170, 1728, 838)
    transition = ("push", "rise")
```

```{lemur-example}
:files: warm/style.py

!slide A warmer journal

The accent, the title colour and the title size come from `style.py`;
everything else is `journal`'s: $\int_0^1 f(x)\,dx$.

- one
- two
```

The shipped themes are importable as `lemur.themes.clean`, `lemur.themes.dark`
and `lemur.themes.journal`. Subclass `lemur.style.Style` itself to start from
the defaults (which are `clean`).

## The fields

The full list is in the [style field reference](../reference/style-fields.md).
In short:

| Group | Fields |
|---|---|
| design box | `width`, `height` (px) |
| colours | `bg`, `title`, `body`, `math`, `caption`, `accent`, `rule` |
| code colours | `code`, `code_bg`, `code_keyword`, `code_string`, `code_number`, `code_comment`, `code_function`, `code_type`, `code_highlight` |
| fonts | `serif` (text), `mono` (code): a tuple of family names, tried in order |
| sizes | `title_size`, `body_size`, `math_size`, `code_size`, `table_size`, `caption_size` (px), `line_height` |
| titles | `title_weight`, `title_spacing`, `title_rule` (accent underline, 0 = none) |
| title slide | `cover_title_scale`, `cover_rule`, `cover_caps` |
| regions | `title_region`, `body_region`: `Region(x, y, w, h)`, `h=None` = grow to content |
| behaviour | `transition = (across, step)`, `preamble` (a LaTeX preamble file) |

Colours are hex strings. Fonts must be installed on the machine that builds the
deck, since text is turned into outlines at build time. The viewer needs no
fonts at all.

## Regions

The title and the body are placed into **regions** of the design box.
`Region(x, y, w, h)` is in design-box pixels (1920×1080 by default). The body
starts right below the title; `body_region.y` is the earliest it may start, so
raise it to reserve room at the top, for instance for a brand bar drawn by a
template. To see the regions of a design, draw them:

```console
$ lmr2svg talk.lmr --wireframe      # writes talk.wireframe.html
```

## A LaTeX preamble

`preamble = "preamble.tex"` (relative to `style.py`) replaces the LaTeX
preamble used for maths: add packages, fonts or macros there. See
[Maths](../guide/maths.md#packages-and-macros).

## Templates in the same file

Besides `Style`, a `style.py` may register **templates**: functions that draw a
kind of slide. That is how to get a brand bar on every slide, a custom title
slide, or a special layout selected with `!slide[.name]`. See
[Templates](templates.md).

## Sharing a design

To use one design in several decks, put it in a theme folder,
`themes/<name>/style.py`, and select it with `!theme <name>`. The folder can
sit next to each deck, or in a place listed in `LEMUR_THEMES` (see
[Themes](themes.md#your-own-theme)).

:::{note}
`style.py` is ordinary Python and runs when the deck is built, like a
`conf.py` in Sphinx. Only use style files you trust.
:::
