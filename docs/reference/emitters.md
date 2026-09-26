# Emitters

lemur separates *what a document means* from *how it looks*. The parser turns
a `.lmr` file into a neutral document tree (the [AST](ast.md)), and an
**emitter** turns that tree into output. The language is the same whichever
emitter you use; this page lists how the emitters differ.

| Emitter | Command | Output | Typesetting |
|---|---|---|---|
| **SVG deck** | `lmr2svg` | one self-contained `.html` file | at build time: Pango for text, LaTeX for maths, all baked to vector outlines |
| **HTML deck** | `lmr2slides` | a folder: `index.html`, stylesheet, runtime, fonts | in the browser: HTML/CSS for text, MathJax for maths |

Use `lmr2svg` unless you have a reason not to. Its output looks identical
everywhere, needs no network, and supports the whole language.

## Support

```{rst-class} support
```

| Feature | `lmr2svg` | `lmr2slides` |
|---|:-:|:-:|
| text, emphasis, smart typography, styled spans | ✓ | ✓ |
| inline and display maths, `\mk` marks | ✓ | ✓ |
| lists, nested lists, `+` reveals | ✓ | ✓ |
| `!pause`, overlays, `!when`, relative steps | ✓ | ✓ |
| `!stack` / `!layer`, `!columns`, `!style`, `!gap` | ✓ | ✓ |
| code blocks with per-step highlights | ✓ | ✓ |
| tables | ✓ | ✓ |
| images, layered images | ✓ | ✓ |
| environments | ✓ | ✓ |
| `!annotate`, `!connect` | ✓ | ✓ |
| references, citations, bibliography, links | ✓ | ✓ |
| title slide, header, footer, logo, slide numbers, progress bar | ✓ | ✓ |
| transitions (`!transition`) | ✓ | ✓ |
| per-slide classes `.center .middle .plain .fill` | ✓ | ✓ |
| per-slide class `.dark` | ✓ | — |
| `!plot` (matplotlib) | ✓ | — |
| `!anim` (`lemur.anim`), with SVG and GPU views | ✓ | — |
| `!shader` (live GLSL) | ✓ | — |
| `!compute` (live WebGPU compute) | ✓ | — |
| design | `style.py` (Python: fields and templates), or a `theme.css` | `theme.css` (CSS custom properties and rules) |
| printing | one page per slide, fully built | one page per step |
| works offline | always | with `--assets` (a local MathJax) |

— : the construct is accepted but not shown.

## `lmr2svg` in detail

- **Layout.** A slide is laid out in its design box at build time. Text is
  shaped by Pango with the design's fonts and turned into outlines; each
  distinct glyph is stored once and reused. Maths is typeset by LaTeX and
  converted to outlines with `dvisvgm`.
- **Annotations** and **connectors** are placed at build time from the real
  glyph boxes.
- **The player.** A small script steps through the slides and animates the
  step reveals and transitions. It also plays `!anim` keyframes (projecting 3‑D
  views on the fly), runs `!shader`s with WebGL 2 and `!compute` programs with
  WebGPU.
- **The still frame.** Every slide is also written in its final state, which
  printing and the overview use.

## `lmr2slides` in detail

- **Layout.** The slide DOM is written at build time, and the browser lays it
  out with CSS in a fixed design box scaled to the window. The deck ships its
  own fonts (OFL), so text wraps identically on every machine.
- **Maths** is typeset by MathJax in the browser, from a CDN or from a local
  copy (`--assets`).
- **Annotations** and **connectors** are measured in the browser from the
  rendered layout.
- **The interface** between the deck's DOM and its runtime is specified in
  `spec/display-contract.md` in the repository, for anyone writing another
  DOM-based emitter.
