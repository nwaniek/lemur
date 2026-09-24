# lemur examples

Each folder is a **standalone example** — a small `.lmr` deck you can build and
open on its own. Together they double as documentation: pick the feature you
want and read its deck.

Everything here targets the **build-time SVG** emitter (`lmr2svg`), which renders
text and maths to baked outlines and emits **one self-contained `.html`** — no
web fonts, no MathJax, nothing fetched at display time.

## Build any example

```sh
# a plain feature deck
python3 lmr2svg.py examples/math/deck.lmr -o math.html

# a deck with its own design — it carries a style.py next to it, picked up
# automatically (no flags); pass --style <path> to point elsewhere
python3 lmr2svg.py examples/corporate/deck.lmr -o corporate.html
```

Open the resulting `.html` in a browser. Navigate with **← / →** (or the wedges,
the mouse wheel, or a click); press **o** for the slide grid, **O** for the
sidebar; the URL tracks `#/<slide>/<step>`.

## Feature galleries — one construct each

| folder | shows |
|---|---|
| [`formatting/`](formatting/) | bold / italic / strike / underline, code, spans, smart typography, styled blocks |
| [`math/`](math/) | inline & display maths, `\mk{}` marks |
| [`lists/`](lists/) | bullet, ordered, nested, step-revealed |
| [`tables/`](tables/) | content-measured columns, per-column alignment, caption |
| [`figures/`](figures/) | an image embedded as a data URI |
| [`code/`](code/) | syntax highlighting + per-step line highlighting |
| [`columns/`](columns/) | weight-split columns and step-swapped stacks |
| [`environments/`](environments/) | `!theorem` / `!proof` / … titled, nestable boxes |
| [`annotations/`](annotations/) | `!annotate` colour+label a mark, `!connect` arrows |
| [`references/`](references/) | `@label` cross-refs, `@key` citations, a bibliography |
| [`transitions/`](transitions/) | step reveals, `!gap`, slide transitions, variant modifiers |
| [`animation/`](animation/) | `!anim` — a build-time animation baked into a slide viewport, one beat per step |
| [`animation3d/`](animation3d/) | `View` — 3D (a helix / complex exponential) — geometry shipped once, projected by the player as the camera moves |
| [`anim-science/`](anim-science/) | `!anim` scientific figures — the Lorenz attractor traced over time, an area sweeping under a curve, a sine from the unit circle |
| [`anim-calculus/`](anim-calculus/) | `!anim` calculus & fields — Taylor series, a square wave from harmonics, Riemann sums, a vector field, a moving tangent |
| [`anim-3d/`](anim-3d/) | `View` building blocks — a wireframe `surface`, multi-view **insets**, synced `trace_dot`s, `legend`/`panel` |
| [`parallel-transport/`](parallel-transport/) | a short **lecture**: a 3D sphere, the tangent space, and holonomy (a vector returns rotated) |
| [`tangent-space/`](tangent-space/) | a short **lecture**: the tangent space of a dome — velocities, `T_pM`, `exp_p`/`log_p` unrolling and shrink-wrapping, the tangent bundle |
| [`tangent-space-illustrated/`](tangent-space-illustrated/) | the same lecture, drawn like a paper figure: lit, opaque surfaces with a silhouette and contact shadow, haloed vectors, paper and ink (`View.shaded_surface`) |
| [`optimal-transport/`](optimal-transport/) | a short **lecture** with a **particle system**: optimal transport on a sphere — geodesic paths, random vs optimal plans, Sinkhorn blur, shapes reshaped (`lemur.anim.illustrate`) |
| [`live-shaders/`](live-shaders/) | **live GPU shaders** on slides (`!shader`): a demoscene homage — aurora, raymarched terrain flyover, volumetric clouds, curl-noise fluid — stepped by the slides, with optional generative sound |
| [`plots/`](plots/) | `!plot` — publication-quality matplotlib figures (scatter, contour, bars, violin) baked to SVG |

## Template mechanism — bring your own design

| folder | shows |
|---|---|
| [`custom-templates/`](custom-templates/) | the smallest custom template: a `@register`ed class selected with `!slide[.banner]` |
| [`corporate/`](corporate/) | a full brand identity in one `style.py` — a `class Style` **and** the templates (brand bar, cover) |
| [`lecture/`](lecture/) | a real multi-file course deck (`!include`), the reference for a longer talk |

## How the design is configured

- **`style.py`** (recommended) — one file next to your `.lmr` holding the whole
  design: a **`class Style`** (subclass a shipped theme or the base and override
  a few fields — colours, sizes, `region`s, a default `transition`) **and** any
  templates (`@register`ed `render(ctx)` functions). Picked up automatically,
  or `--style <path>`. Register a built-in name (`content`/`cover`/`section`) to
  restyle every slide of that kind, or a new name to select per slide with
  `!slide[.name]`. Registrations are isolated per build. See `corporate/style.py`
  and `custom-templates/style.py`.
  ```python
  from lemur.themes import journal
  from lemur.style import Style, Region
  class Style(journal.Style):        # inherit journal, tweak one field
      accent = "#c8a24a"
  ```
- **Shipped themes** — `lemur/themes/{clean,dark,journal}.py`; use with `--theme
  clean|dark|journal` or `!theme <name>` for a quick palette swap with no files
  of your own, or subclass one in a `style.py` as above.
