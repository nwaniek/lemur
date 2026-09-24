# Plots (matplotlib)

`python3 lmr2svg.py examples/plots/deck.lmr -o plots.html`  (needs `pip install lemur[plot]`)

- `!plot` with `!src <module.py>` runs a **matplotlib** script at build time and
  bakes the figure to a **self-contained SVG** (text as outlines, `svg.fonttype
  = "path"`), placed like `!img` with `!caption`/`!width`. matplotlib does the
  heavy lifting — ticks, axis labels, legends, colorbars, arrows, every plot type.
- The script hands lemur a `Figure`: define `figure()` (or `plot()`), assign a
  module-level `fig`, or just leave the current pyplot figure.
- Gallery: `scatter.py` (fit + legend + arrow annotation), `contour.py`
  (filled contours + colorbar), `bars.py` (grouped bars + error bars), and
  `violin.py` (distributions). Use them as starting points for your own figures.
