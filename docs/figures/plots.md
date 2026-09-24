# Plots

`!plot` runs a Python script that draws a figure with **matplotlib**, and
places the result on the slide like an image: sharp at any size, with its text
turned into outlines, and embedded in the deck. matplotlib does the hard work
(axes, ticks, legends, colour bars, every kind of plot), and lemur takes care of
placing the figure.

```{lemur-example}
:files: plot/posterior.py
:source:

!slide The posterior sharpens

!plot Posterior over time ^post
	!src posterior.py
	!caption Three posteriors of a coin's bias, after 4, 20 and 100 flips.
	!width 70%
```

`!plot` needs matplotlib: `pip install -e '.[plot]'`.

## The script

The script is an ordinary Python module next to the `.lmr` file. It hands lemur
its figure in one of three ways, tried in this order:

1. a function `figure()` (or `plot()` or `make_figure()`) that returns a
   matplotlib `Figure`;
2. a module-level variable `fig`;
3. whatever the current pyplot figure is after the module has run.

The first is the cleanest. The script runs once per build. If it raises an
error, the build reports it with the slide and leaves the figure out; the rest
of the deck still builds.

## Directives

| Directive | Meaning |
|---|---|
| `!src file.py` | the script (required) |
| `!caption text` | a caption below the figure |
| `!width`, `!height` | the size, as for [images](../guide/images.md): a percentage of the text column, or a length |

As with `!img`, a title and `^ref` on the `!plot` line make the figure a
target for `@ref`.

## Tips

- **Size the figure for the slide.** `figsize` sets the aspect ratio and the
  size of the text relative to the plot, and `!width` scales the whole figure.
  A wide `figsize` such as `(8, 4)` suits a 16:9 slide.
- **Match the deck.** Set colours and fonts in the script, or in a shared module
  your plot scripts import, so all figures look alike.
- **Maths in labels** uses matplotlib's mathtext (`r"$\theta$"`), which is
  close to, but not the same as, the deck's LaTeX.
- **Build up a figure in steps** by making one `!plot` per stage inside a
  `!stack` (see [Stacks](../guide/steps.md#stacks-things-that-take-each-others-place)),
  or animate it with [`!anim`](animations.md).

The `plots` example has a gallery to start from: a scatter plot with a fit,
filled contours with a colour bar, grouped bars with error bars, and violin
plots.
