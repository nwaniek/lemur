# lemur

**disclaimer**: This is an experiment in vibe coding. That is, the lemur
language itself as well as the first converter from lemur to html slides were
manually designed and built, but everything that came after, in particular
adding animations, vonerting to svg, adding webgl, etc. was done using various
AIs to figure out how well they perform when clear requirements were engineered
and presented.


**lemur** (`.lmr`) is a light markup language for slides and technical writing —
reStructuredText-like blocks, Markdown-like inline marks and LaTeX maths — and a
toolchain that turns it into presentations.

```
!title  Belief Propagation
!author Ada Lovelace

!slide Messages on a tree ^bp

A factor sends each neighbour the product of what it heard, summed over the rest:

:: math
	\mu_{a \to x}(x) = \mk{sum}{\sum_{x_{\partial a} \setminus x}} f_a
		\mk{prod}{\prod_{y} \mu_{y \to a}(y)}

!annotate
	prod: collect incoming messages
	sum[#7a4b94]: marginalise the rest

+ exact on trees
+ a good approximation on loopy graphs
```

The main tool, **`lmr2svg`**, compiles a deck to **one self-contained `.html`
file**. Text is set with Pango and maths with LaTeX at build time, and both are
baked into vector outlines. The file needs no web fonts, no MathJax and no
network: it looks the same on every machine, and it works offline in any lecture
hall.

The full documentation (a tutorial, a guide to every construct with live
examples, and references for the command line, `style.py` and `lemur.anim`) is
in [`docs/`](docs/). Build it with `make docs` (needs `pip install -e '.[svg,docs]'`)
and open `build/docs/index.html`.

- [Installation](#installation)
- [Quickstart](#quickstart)
- [The language at a glance](#the-language-at-a-glance)
- [Presenting](#presenting)
- [Design: themes, `style.py` and templates](#design-themes-stylepy-and-templates)
- [Figures that compute: `!plot`, `!anim`, `!shader`, `!compute`](#figures-that-compute-plot-anim-shader-compute)
- [Diagnostics](#diagnostics)
- [The toolchain](#the-toolchain)
- [Examples](#examples)
- [Development](#development)

## Installation

lemur needs Python ≥ 3.10. The parser has no dependencies of its own. The
`lmr2svg` build also needs the following:

| what | for |
|---|---|
| `numpy`, `pycairo`, `PyGObject` (Pango) | text shaping and outlines |
| a TeX distribution with `latex` and `dvisvgm` on `PATH` | maths |
| `pygments` | syntax highlighting of code blocks |
| `matplotlib` (optional) | `!plot` figures |

```sh
pip install -e '.[svg]'          # add ,plot for matplotlib figures
```

This installs the commands `lmr2svg`, `lmranim`, `lmr2slides` and `lmr2ast`. You can also
run the tools straight from a checkout with `python3 lmr2svg.py …`.

LaTeX results are cached on disk, so a rebuild only typesets what changed. The
cache lives in `$XDG_CACHE_HOME/lemur`, or in `$LEMUR_CACHE` if that is set.

## Quickstart

```sh
python3 lmr2svg.py talk.lmr -o talk.html     # build once
python3 lmr2svg.py talk.lmr --watch          # serve with live reload while you write
python3 lmr2svg.py talk.lmr --strict         # fail (exit 3) on any warning, e.g. in CI
python3 lmranim.py hello.py                  # design one animation: timeline, rebuild on save
```

Open `talk.html` in a browser. Other options:

| option | effect |
|---|---|
| `-t, --theme NAME` | a shipped theme (`clean`, `dark`, `journal`) or a `themes/<name>/` folder next to the deck |
| `-s, --style FILE` | a `style.py` holding the design and templates (default: `style.py` next to the deck) |
| `-q, --quality LEVEL` | curve precision: `draft`, `low`, `medium`, `high`, `max` |
| `--separate-images` | write a folder with `images/` instead of embedding images in the file |
| `--wireframe` | draw the design's regions as labelled boxes, for designing templates |
| `-p, --port`, `--no-open` | port and browser behaviour for `--watch` |

A longer talk is usually a `master.lmr` holding the configuration plus one
`!include`d file per chapter.

## The language at a glance

The complete language is specified in [`spec/spec.lmr`](spec/spec.lmr), which is
itself written in lemur. The short version:

**One uniform directive shape.** Every directive is
`!name[options]<overlay> text ^ref`:
- options (style classes, sizes, widths, line ranges) go in `[…]`;
- *when to show* goes in `<…>`;
- the bare tail is human text (a title or caption);
- `^ref` labels the thing so `@ref` can point to it.

A bracket always touches the directive, with no space in between.

**Inline marks:**

| Mark | Meaning |
|---|---|
| `**bold**`, `__italic__`, `~~strike~~`, `++underline++`, `` `code` `` | emphasis and code |
| `$…$` | inline LaTeX maths |
| `[text]{.class #color bg:#eef}` | a styled span |
| `[text]^name` | a named mark (for annotations and arrows) |
| `[text]<2->` | an inline run revealed on a step |
| `@ref`, `[text]@ref` | cross-references |
| `@key`, `@(k1, k2)` | citations |
| `<https://…>` | a link |

Smart typography turns `--`, `---` and `...` into dashes and an ellipsis, and
curls straight quotes. Code and maths are never touched.

**Blocks:**

| Construct | Syntax |
|---|---|
| slides and sections | `!slide[.style] Title ^ref`, `# Section`, `##`/`###` headings in a slide |
| lists | `-`/`*` static, `+` revealed one per step, `1.` ordered; nest by indenting |
| display maths | `:: math` with an indented LaTeX body; `\mk{name}{…}` names a part |
| code | `:: python`, or `:: python[1\|4-6]` to step through highlighted lines |
| tables | `!table`, `!cols A, B[r], C[c]`, `!caption`, indented rows; any punctuation separates columns |
| images | `!img` with one or more `!src` (layers revealed step by step), `!caption`, `!width` |
| layout | `!columns[60 40]` / `!column`, `!stack` / `!layer<spec>`, `!style[.frame]`, `!gap[fill]` |
| environments | `!theorem`, `!lemma`, `!definition`, `!proof`, `!example`, `!remark`, `!note`, `!warning`, … |
| step control | `!pause`, `!when<2-4>` blocks, relative `<+->` / `<+>` |
| explanation | `!annotate` (colour a mark and label it with an arrow), `!connect` (an arrow between two marks) |
| references | `^key: entry` bibliography lines, `^name: <url>` link targets |
| computed figures | `!plot`, `!anim`, `!shader`, `!compute` (see below) |
| other | `!notes` (speaker notes, not shown), `!include file.lmr`, `%%` comments |

Blocks are delimited by indentation. The first line of a body sets its
indentation, and every following line must start with exactly that prefix. Tabs
or spaces are the author's choice, and no tab width is assumed.

**Steps.** Each slide has one integer step:
- step 0 is the slide as it opens, and every keypress advances it by one;
- `!pause`, `+` items, image layers, code highlight groups, and `!annotate`
  and `!connect` lines all take steps from the same counter, in reading order;
- once everything on the slide has been revealed, the steps of its animations
  and shaders follow;
- overlay specs (`<2>`, `<2->`, `<-3>`, `<2-4>`, `<+->`) show a thing on chosen
  steps, and can hide it again.

**Configuration.** Put these before the first slide:
- talk details: `!title`, `!subtitle`, `!author`, `!institute`, `!date`,
  `!titleimage`, `!logo`;
- chrome: `!header`, `!footer`, `!slidenumbers on|off`, `!progress top|bottom`;
- look: `!theme`, `!aspect 16:9|4:3`, `!transition <slide> [<step>]`. Slide
  transitions are `none`, `fade`, `slide` or `push`; step reveals are `none`,
  `fade` or `rise`.

## Presenting

| key | action |
|---|---|
| → Space PageDown, click, wheel down | next step |
| ← PageUp, wheel up | previous step |
| ↓ / ↑ | next / previous slide |
| Home / End | first slide / end of the talk |
| `o` | slide overview grid (arrows + Enter or a click to jump, Esc to close) |
| `O` | thumbnail sidebar next to the live slide |
| `m` | toggle the soundtrack of a `!shader` slide that has one |

The URL tracks `#/<slide>/<step>`, so every moment of a talk is linkable and
survives a reload.

**Printing.** The browser's print dialog prints one page per slide, each in its
final state. Save to PDF there for handouts.

## Design: themes, `style.py` and templates

A deck is laid out in a fixed design box, 1920×1080 by default or 1440×1080 with
`!aspect 4:3`. That box is scaled to the window as a whole, so nothing reflows
between machines.

**Themes.** Three themes ship with lemur: `clean` (the default), `dark` and
`journal`. Pick one with `!theme <name>` in the deck or `--theme <name>` on the
command line. A deck can also carry `themes/<name>/` next to it; more folders
can be listed in `$LEMUR_THEMES`. Such a folder holds either a `style.py` or a
CSS `theme.css`, whose `--lmr-*` tokens (fonts, sizes, colours, padding) are
mapped onto the design.

**`style.py`.** The whole design fits in one Python file next to the deck,
picked up automatically. A `class Style` subclasses a shipped theme and
overrides fields such as colours, fonts, sizes, regions, the default transition
and a LaTeX preamble:

```python
from lemur.style import Style, Region
from lemur.themes import journal

class Style(journal.Style):
    accent = "#c8a24a"
    body_region = Region(80, 320, 1760, 610)
    transition = ("push", "rise")
```

**Templates.** The same file can register templates: plain `render(ctx)`
functions that draw a slide with helpers such as `line`, `flow`, `header`,
`footer`, `logo` and `region`.
- A template registered under a built-in name (`content`, `cover`, `section`)
  restyles every slide of that kind.
- A template under a new name is chosen per slide with `!slide[.name]`.

```python
from lemur.style import register, line, flow

@register("banner")
def banner(ctx):
    d = ctx.design
    ctx.slide.add_rect(0, 0, d.width, 300, d.accent)
    line(ctx, ctx.title, 88.0, 96.0, (140.0, d.width - 280.0), "#ffffff", weight=700)
    flow(ctx, ctx.blocks, (140.0, d.width - 280.0), 420.0)
```

Slide classes that are not templates act as layout modifiers:
- `.center` / `.middle` centre the body horizontally / vertically;
- `.plain` hides the header and footer;
- `.fill` drops the padding.

`style.py` runs at build time as trusted code. See `examples/custom-templates/`
and `examples/corporate/`.

## Figures that compute: `!plot`, `!anim`, `!shader`, `!compute`

**`!plot`** runs a matplotlib script at build time and places the figure as a
self-contained vector image. It takes `!caption` and `!width` like `!img`.

```
!plot Posterior ^post
	!src posterior.py
	!width 70%
```

The script provides a `Figure`: a `figure()` or `plot()` function, a
module-level `fig`, or simply the current pyplot figure.

**`!anim`** embeds an animation written in Python with `lemur.anim`, a
manim-style library:
- shapes, text and maths, `Create` / `FadeIn` / `Transform`, value trackers and
  updaters;
- each `self.next()` is one slide step, and the player tweens between steps in
  real time;
- `!viewport` places it on the slide: `body` (the default), `full`, or an
  `x y w h` rectangle.

```python
from lemur.anim import Anim, Circle, Create, RIGHT

class Hello(Anim):
    def build(self):
        c = Circle()
        self.play(Create(c))
        self.next()                        # one slide step
        self.play(c.animate.shift(RIGHT * 2))
```

While you write an animation, **`lmranim`** shows it on its own with a
timeline. It rebuilds on every save and keeps the playhead where it was. You
can step through beats and frames, loop one beat, and overlay a coordinate grid.
Clicking a shape opens the line that created it in your editor:

```sh
LEMUR_EDITOR='vim --servername lemur --remote-silent +{line} {file}' lmranim hello.py
```

3‑D goes through a `View`, which is a camera plus a viewport on the slide:
- **Building blocks:** curves, surfaces, lit and shaded meshes, solids, axes,
  labels pinned to 3‑D points, and moving curves.
- **What the file stores:** a view's shapes are saved once as 3‑D geometry plus
  the camera's path. The deck's player projects them every frame, so orbiting a
  large mesh adds almost nothing to the file.
- **Occlusion:** give a view an `occluder` (a sphere or a dome) and the player
  also hides, dashes or dims what goes behind it.
- **GPU views:** `View(renderer="gpu")` draws a view with WebGL and a depth
  buffer, so any surface hides anything (a torus, a saddle, several objects).
  Print and PDF get an exact vector still of it.
- **Illustrated style:** `lemur.anim.illustrate` draws paper-style figures with
  soft lighting, silhouettes, contact shadows and haloed curves.

**`!shader`** runs a GLSL fragment shader live on the GPU (WebGL 2). It uses
Shadertoy's `mainImage` convention and uniforms, plus lemur's own:
- `iStep` is the slide step, eased so that a keypress glides the scene to its
  next state; `iStepRaw` and `iSteps` are also available;
- `!steps N` gives the shader its own steps;
- `!viewport full` draws it behind the slide's text;
- `!quality` caps the resolution, which also adapts on its own;
- `!sound drone|aurora` adds a generative soundtrack, off until you press `m`;
- `#include "file.glsl"` is resolved at build time.

The overview and print show the last rendered frame.

**`!compute`** runs a WebGPU program live: `@compute` kernels over storage
buffers, thousands or millions of threads at a time, and a `mainImage` that
draws the result. It suits parallel algorithms (reductions, atomics, scans) and
simulations (particles, reaction–diffusion, cellular automata).
- Buffers are declared in the WGSL with fixed sizes; lemur reads them and each
  kernel's `//! threads N` annotation at build time, and reports mistakes with
  their line.
- The simulation runs with a fixed timestep (`!rate`) and seed. Its state is
  saved at every step, so going back restores it, and jumping ahead replays it.
- `!steps N` gives it steps of its own; `!steps slide` makes it follow the
  slide's own steps, for example in step with a highlighted code block.
- It needs a browser with WebGPU. Elsewhere the slide shows a notice.

## Diagnostics

A build does not fail on a problem in one slide; it reports the problem and
carries on:
- a LaTeX error renders the offending source in red and warns;
- a missing image becomes a placeholder;
- unresolved references and citations, unknown themes, table rows whose cell
  count does not match the columns, content that overflows a slide, and
  equations, tables or code wider than their column are reported per slide;
- a too-wide equation is scaled down to fit.

`--strict` turns any warning into a failed build.

Structural errors are reported with file and line and stop the build. Examples
are inconsistent indentation, an unknown directive, or a block missing its
body.

## The toolchain

lemur is a **parser → AST → emitter** pipeline. The parser (`lemur.parser`)
reads `.lmr`, resolves `!include`s, steps and references, and produces a neutral
JSON AST. The AST is specified by [`spec/ast.schema.json`](spec/ast.schema.json)
and knows nothing about any output format. Emitters turn it into output.

| command | output |
|---|---|
| `lmr2svg` | **one self-contained HTML file**: text and maths baked to SVG outlines at build time, a small player for steps, transitions, animations, shaders and compute programs. Supports the whole language. |
| `lmr2slides` | an HTML/CSS deck *folder*: the slide DOM is written at build time, and maths is typeset in the browser by MathJax. It supports the core language and slide layer, but not `!plot`, `!anim`, `!shader` or `!compute`. |
| `lmr2ast` | the AST as JSON, for inspection or for your own emitter |
| `lmranim` | not an emitter: a live viewer for one `lemur.anim` module, with a timeline, rebuild on save and jump-to-source |

### `lmr2slides`

```sh
python3 lmr2slides.py talk.lmr -o build/talk           # index.html, slides.css, runtime.js, fonts/
python3 lmr2slides.py talk.lmr -o build/talk --print   # build print pages eagerly (PDF via headless Chrome)
python3 lmr2slides.py --list-themes
```

This deck is a folder containing `index.html`, the stylesheet, the runtime and
the bundled OFL fonts. Its themes are CSS files: `lemur/assets/themes/<name>/theme.css`
on top of `lemur/assets/base.css`. They are chosen with `--theme`, `--theme-dir`,
`$LEMUR_THEMES`, `themes/` next to the deck, or the built-in set (`clean`,
`dark`, `journal`, `gradient`, `corporate`).

MathJax loads from a CDN unless `--assets DIR` points at a local MathJax 4
install (`DIR/mathjax/tex-svg.js`), which makes the deck work offline. Printing
gives one page per cumulative step. `node tools/pdf.mjs build/talk talk.pdf`
renders the PDF headlessly.

Arrows from `!annotate` and `!connect` are measured in the browser at display
time; in `lmr2svg` they are computed at build time. The display contract
between this deck's DOM and its runtime is described in
[`spec/display-contract.md`](spec/display-contract.md).

## Examples

[`examples/`](examples/) has one small deck per feature: formatting, maths,
lists, tables, figures, code, columns, environments, annotations, references
and transitions. It also has the design mechanisms (`custom-templates`,
`corporate`) and complete talks:
- `lecture`, a multi-file course deck;
- `tangent-space` and `tangent-space-illustrated`, which use 3‑D animation;
- `torus`, which uses GPU views;
- `optimal-transport`, a particle system on a sphere;
- `parallel-transport`;
- `live-shaders`, a demoscene-style deck with GPU shaders and sound;
- `compute`, WebGPU compute shaders: a parallel reduction, atomics, reaction–diffusion and particles.

Each folder has a README.

```sh
make examples            # build every example into build/examples/
```

## Development

```sh
make python              # parser, emitters, animation IR (unittest)
python3 -m pytest -q tests/python
```

A few Python tests run the 3‑D projection maths in both Python and the
browser's JavaScript, and need `node` for that. The browser runtime of
`lmr2slides` has its own harness in `tests/js/`: `npm install`, then `npm test`.
It uses jsdom, plus puppeteer-core against a system Chrome (`$CHROME`).

Layout of the package:

| path | contents |
|---|---|
| `lemur/parser.py`, `lemur/ast.py` | the language: parser, diagnostics, AST |
| `lemur/emit/svg.py` | the `lmr2svg` emitter |
| `lemur/emit/slides.py`, `lemur/emit/html.py` | the `lmr2slides` emitter |
| `lemur/typeset/` | Pango text, LaTeX maths, outline geometry, the on-disk cache |
| `lemur/style.py`, `lemur/master.py`, `lemur/themes/` | the design box, `style.py` API, shipped themes |
| `lemur/anim/` | `lemur.anim`: shapes, animations, 3‑D views, the keyframe IR |
| `lemur/animview.py` | `lmranim`, the animation viewer (its page chrome is `assets/svg/animview.*`) |
| `lemur/wgsl.py` | reads a `!compute` program's buffers and kernels at build time |
| `lemur/assets/svg/` | the player of an `lmr2svg` deck (`runtime.js`, `world.js`, `gl.js`, `shader.js`, `compute.js`) |
| `lemur/assets/` | runtime, CSS, themes and fonts of `lmr2slides` decks |
| `spec/` | the language spec, the AST schema, the display contract |
