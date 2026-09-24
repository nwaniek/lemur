# Illustrated figures

`lemur.anim.illustrate` draws 3‑D figures the way a geometry paper does:

- an **opaque, softly lit surface** with a faint mesh;
- a **crisp silhouette** and a **soft contact shadow**;
- curves, vectors and dots on top, each on a **paper-white halo**;
- hidden parts drawn as technical illustrations draw them: curves thin, dashed
  and faint, dots hidden, and vectors and sheets fading to a ghost.

Everything stays correct as the camera moves.

```{lemur-example}
:step: 1
:files: ill/globe.py
:source:

!slide A geodesic on a sphere

!anim
	!src globe.py
```

## A figure

A `Figure` bundles a [view](3d.md) (the camera), an **occluder** (the solid that
hides things) and a **palette**:

```python
from lemur.anim import View
from lemur.anim.illustrate import Figure, Sphere, PAPER

fig = Figure(View(azim=-30, elev=22, scale=1.55), Sphere(2.0), PAPER)
shadow, solid, outline = fig.backdrop()     # add these first
```

`Sphere(radius, center=(0, 0, 0), cap_z=None)` is a solid sphere. With
`cap_z=0` it becomes a dome standing on the plane *z = 0*.

## The vocabulary

| Method | Draws |
|---|---|
| `fig.backdrop(nu=40)` | `(shadow, solid, silhouette)`: the lit occluder with its outline and contact shadow |
| `fig.shaded(fn, u_range, v_range)` | any other lit, opaque surface |
| `fig.curve(points_fn, color=…, width=4, closed=False)` | a haloed curve; its hidden part is dashed (`hidden=None` drops it), and `occlude=False` draws it whole |
| `fig.dot(where, color=…, ghost=False)` | a dot with a paper rim; it hides behind the occluder (`ghost=True`: it fades instead) |
| `fig.arrow(state)` | a fat vector from `state()[0]` along `state()[1]`, on a halo; faint while its base is hidden |
| `fig.sheet(corners_fn, grid=4, anchor=…)` | a translucent sheet (a tangent plane) with a fine grid; faint while `anchor()` is hidden |
| `fig.label(tex, where, offset=(dx, dy))` | LaTeX in ink, pinned next to a 3‑D point |

Arguments that end in `_fn`, and `where`, `state` and `anchor`, may be
functions that are evaluated on every frame. Hand them a `ValueTracker`-driven
function, and the curve grows, the dot walks and the vector turns along with
it. `fig.curve` returns a group of parts (the hidden line, the halo, the line),
so animate it with `*[Create(m) for m in curve]`.

## Palettes

`PAPER` (ink on warm paper) and `NIGHT` (light on a dark ground) ship with the
module. A `Palette` is a small dataclass of colours: `paper`, `ink`,
`shade_dark`/`shade_light` (the lighting ramp of the surface), `fill_light`,
`sheet_fill`/`sheet_edge`, `shadow`, and the accents `orange`, `red`, `blue`,
`green` and `purple`. Make your own with `Palette(ink="#…", …)`.

## Limits

The occluder is convex: a sphere, or a dome. Curves and dots are hidden against
it exactly. Other surfaces drawn with `fig.shaded` hide their own back faces
but not what is behind them.

The `tangent-space-illustrated` example is a whole lecture in this style, and
`optimal-transport` adds a particle system of 180 points on a sphere.
