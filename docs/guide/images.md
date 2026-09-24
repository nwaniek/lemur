# Images

An `!img` block places an image. `!src` is the only required directive:

```{lemur-example}
:files: diagram.svg

!slide An image

!img A tiny factor graph ^fg
	!src diagram.svg
	!caption Two variables and one factor.
	!width 55%
```

| Directive | Meaning |
|---|---|
| `!src path` | the image file: a path relative to the `.lmr` file (SVG, PNG, JPEG, …) |
| `!caption text` | a caption below the image (inline markup and maths allowed) |
| `!width`, `!height` | the size. A percentage is a fraction of the text column, like `\includegraphics[width=0.55\textwidth]`; a length such as `600px` is absolute |
| `!mode overlay\|replace` | how extra layers combine (see below) |

The title and `^ref` on the `!img` line make the image a target for
`@fg`.

`lmr2svg` embeds images in the output, so a deck stays one file. For decks with
many large photos, `--separate-images` writes a folder instead: the deck's
`index.html` with the images beside it in `images/`. A missing image does not stop the build: its place is marked, and the
build reports it.

## Images that build up

Several `!src` lines make **layers** on one canvas. The first is shown with the
slide, and each further layer arrives on its own step. That is the natural way
to build up a diagram exported from a drawing program, one layer per stage:

```{lemur-example}
:files: fg_layer1.svg fg_layer2.svg fg_layer3.svg

!slide Building up a factor graph

!img
	!src fg_layer1.svg
	!src fg_layer2.svg
	!src fg_layer3.svg
	!caption Nodes, then edges, then messages.
	!width 60%
```

With `!mode overlay` (the default), each new layer is drawn over the previous
ones, so transparent layers add to the picture. With `!mode replace`, each
layer replaces the one before.

:::{tip}
To build a TikZ figure up in steps, export each stage to SVG at the same canvas
size (for example with `dvisvgm`, or with one Inkscape layer per stage) and list
the files as successive `!src` lines.
:::

## Computed figures

When a figure is better computed than drawn, `!plot` runs a matplotlib script
and places the result like an image. See [Plots](../figures/plots.md).
