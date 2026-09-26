# Architecture

lemur is a pipeline: **parser → AST → emitter**.

```text
 talk.lmr ──► parser ──► AST (JSON) ──► emitter ──► output
 (+ includes)  lemur.parser   spec/ast.schema.json   lmr2svg: one .html
                                                    lmr2slides: a deck folder
```

## The parser (`lemur.parser`)

The parser has no dependencies. It reads the master file, resolving `!include`s
and remembering file and line numbers for every line, and it parses the
document in one pass:

- **Blocks** are recognised by their first characters (`!`, `::`, `#`, list
  markers, `^key:`). A body is delimited by indentation, with the first line
  fixing the prefix.
- **Steps** are allocated in reading order. `+`, `!pause`, code highlight
  groups, image layers, and annotate and connect lines each take the next
  step. Relative overlays (`<+->`) are resolved to concrete specs. The AST
  carries only specs, never step counters.
- **References** are collected: labels (`^ref`), bibliography entries and named
  links. Unknown references are reported.
- **Inline markup** is parsed per prose run. Code, maths and URLs are lifted
  out first, so smart typography and escapes never touch them.

Errors that make the document ambiguous (indentation, unknown directives,
missing bodies) are raised with file and line. Things that are merely
suspicious (`$$`, reused marks, table rows that don't split evenly) are
warnings.

## The AST (`lemur.ast`, `spec/ast.schema.json`)

A neutral, versioned JSON tree that describes the document, not a rendering:
see [The AST](../reference/ast.md). Everything an emitter needs is in it, and
nothing that belongs to one output format.

## `lmr2svg` (`lemur.emit.svg`)

| Part | Role |
|---|---|
| `lemur.typeset` | text shaping with Pango (runs → glyph outlines); maths with `latex` + `dvisvgm`; the LaTeX cache; Unicode-to-TeX translation |
| `lemur.layout` | the block layout engine: paragraphs, lists, tables, code, columns, collapsing margins, overflow checks |
| `lemur.master`, `lemur.style`, `lemur.themes` | the design box (`Style` → `Design`), shipped themes, theme lookup, `style.py` loading |
| `lemur.emit.svg` | pagination, templates (`content`, `cover`, `section`, and any registered in a `style.py`), annotations and connectors, figures, `!plot`, `!anim`, `!shader`, `!compute`, and assembly of the deck |
| `lemur.render` | the slide as SVG: each distinct glyph outline is stored once and placed by reference; the step gates of every element |
| `lemur.wgsl` | reads a `!compute` program's buffers and kernels out of its WGSL at build time |
| `lemur/assets/svg/` | the player that ships in every deck: `runtime.js` (navigation, steps, transitions, the overview, the animation player), `world.js` (3‑D projection, meshes, hidden lines and vector stills, only in decks that need it), `gl.js` (the WebGL renderer, only in decks with GPU views), `shader.js` (WebGL, only in decks with shaders) and `compute.js` (WebGPU, only in decks with `!compute`) |

Each slide becomes one inline SVG, with every element gated on the steps it is
visible for. The player only switches visibility and runs animations; it never
lays anything out.

## `lemur.anim`

An animation runs at build time. `Anim.build()` plays animations on shapes, and
the recorder samples every shape's state (outline, colours, opacity, draw
range) at a fixed rate. The keyframe tracks are simplified until linear
interpolation reproduces the samples within a fraction of a pixel. Shapes that
only move are stored as transforms of one outline, and glyphs share outlines.
Shapes made through a 3‑D `View` are stored as 3‑D points plus the camera's
angles, and the player projects them. `lemur/anim/world.py` and
`lemur/assets/svg/world.js` hold the same projection maths, and a test keeps
them in agreement.

## `lmr2slides` (`lemur.emit.slides`, `lemur.emit.html`)

It writes the slide DOM at build time, with CSS themes and MathJax in the
browser. Its DOM and runtime interface is specified in
`spec/display-contract.md`.
