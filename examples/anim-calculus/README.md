# Calculus & fields, animated

`python3 lmr2svg.py examples/anim-calculus/deck.lmr -o anim-calculus.html`

Five `!anim` figures with text and formulas (`MathTex`) baked in — one beat per step:

- **`taylor.py`** — Taylor polynomials of `sin x` converging to it (`Transform` between
  successive curves), the formula updating alongside.
- **`fourier.py`** — a square wave building from its odd harmonics (Gibbs ripples and all).
- **`riemann.py`** — midpoint Riemann sums refining `n = 4 → 8 → 16 → 32` toward the area.
- **`field.py`** — a vector field of `Arrow`s with a streamline traced through it.
- **`tangent.py`** — the derivative as a tangent line sliding along a curve.

Techniques on show: a 2-D plot is a top-down `View` view — `sp.axes(..., numbers=True)`,
`sp.plot(fn, x0, x1)`, `sp.point(x, y)`, with `MathTex` formulas, `Arrow`s, `Transform`
between curves (`static=True`), and `ValueTracker`-driven updaters.
