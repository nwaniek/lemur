# Themes

Every slide is laid out in a fixed **design box**, 1920×1080 pixels (or
1440×1080 with `!aspect 4:3`), and the box as a whole is scaled to the screen.
Nothing reflows between a laptop and a projector, and a slide that fits when
you write it fits when you present it.

A **theme** fills that box with a look: colours, fonts, type sizes, regions,
transitions.

## Shipped themes

```{lemur-example}
:theme: clean

!slide clean — the default

Sans-serif on white with a teal accent, $\int_0^1 f(x)\,dx$, and `code()`.
```

```{lemur-example}
:theme: dark

!slide dark

Light text on a near-black ground, for dim lecture halls: $\int_0^1 f(x)\,dx$
and `code()`.
```

```{lemur-example}
:theme: journal

!slide journal

A serif face on warm paper, like a printed paper: $\int_0^1 f(x)\,dx$ and
`code()`.
```

Choose one in the deck's configuration or on the command line:

```lemur
!theme journal
```

```console
$ lmr2svg talk.lmr --theme dark
```

## Your own theme

There are three ways to go beyond the shipped themes. They differ in how much
they can change:

1. **A `style.py` next to the deck** holds the whole design in one Python file:
   colours, fonts and sizes, the layout regions, the default transition, a
   LaTeX preamble, and custom slide templates. This is the recommended way; see
   [`style.py`](style.md).
2. **A theme folder**, `themes/<name>/` next to the deck, holding a `style.py`
   (or a `theme.css`, see below), selected with `!theme <name>`. Use this to
   keep several designs side by side, or to share one between decks. More
   folders can be added to the search path with the `LEMUR_THEMES` environment
   variable (separated by `:`, or `;` on Windows).
3. **A `theme.css`** with `--lmr-*` custom properties (colours, font families,
   font size, padding). lemur maps these tokens onto the design, so a CSS theme
   written for an HTML deck carries over. Only the tokens count; other CSS rules
   are ignored.

## Which design wins

When several are given, the first of these applies:

1. `--theme NAME` on the command line;
2. a `style.py`: the one given with `--style`, else one next to the deck;
3. `!theme NAME` in the deck;
4. the default, `clean`.

## Per-slide variants

A slide can deviate from the theme with a class: `!slide[.dark]` shows that
slide in a dark variant of the theme, and `.plain`, `.center`, `.middle` and
`.fill` change its layout (see
[per-slide classes](../guide/structure.md#per-slide-classes)). A `style.py`
can add named slide designs of its own: see [Templates](templates.md).
