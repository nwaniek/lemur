# lemur

**lemur** (`.lmr`) is a light markup language for slides and technical writing,
and a toolchain that turns it into presentations. It reads like a plain-text
note. Blocks come from reStructuredText, inline marks from Markdown and maths
straight from LaTeX. A few directives that start with `!` cover what a talk
needs: build-up steps, annotated equations, columns, figures, animations.

```{lemur-example}
:step: last

!slide Messages on a tree

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

Every example in this documentation is built by lemur while the documentation
is built. The preview under the source is the real output: click it (or use the
arrow keys) to step through it.

## What you get

**One file per talk.** `lmr2svg` compiles a deck to a single, self-contained
`.html` file. Text is set with Pango and maths with LaTeX at build time, and both
are baked into vector outlines. The file needs no web fonts, no MathJax and no
network. It looks the same on every machine and works offline in any lecture
hall.

**Build-up without bookkeeping.** Every slide has one integer *step*: bullets,
code highlights, annotations, figure layers and animation beats all advance
it. Relative overlays (`<+->`) let you reorder and copy content without
renumbering anything.

**Explained equations.** Name a part of an equation, then colour it and point
at it with a label, one step at a time. There are no coordinates to maintain.

**Figures that compute.** Put a matplotlib figure on a slide with `!plot`. With
`!anim`, animate with a manim-style library that includes 3‑D views. With
`!shader`, run a GLSL shader live on the GPU, and with `!compute`, run WebGPU
compute kernels: simulations and parallel algorithms, live and in step with
the talk.

**Design in one file.** Pick a theme, or restyle everything from a `style.py`
next to the deck: colours, fonts, regions, and slide templates written in
Python.

## Where to start

- New to lemur? [Install it](getting-started/installation.md) and follow
  [your first talk](getting-started/first-talk.md).
- Writing slides? The [guide](guide/index.md) walks through every construct.
- Looking something up? The [syntax reference](reference/syntax.md) is one
  page, and the [command-line reference](reference/cli.md) lists every option.

```{toctree}
:caption: Getting started
:hidden:

getting-started/installation
getting-started/first-talk
```

```{toctree}
:caption: Writing slides
:hidden:

guide/index
guide/structure
guide/text
guide/lists
guide/steps
guide/maths
guide/annotations
guide/code
guide/tables
guide/images
guide/layout
guide/environments
guide/references
```

```{toctree}
:caption: Design
:hidden:

design/themes
design/style
design/templates
```

```{toctree}
:caption: Figures that compute
:hidden:

figures/plots
figures/animations
figures/viewer
figures/3d
figures/illustrated
figures/shaders
figures/compute
```

```{toctree}
:caption: Presenting & building
:hidden:

presenting/presenting
presenting/building
```

```{toctree}
:caption: Reference
:hidden:

reference/syntax
reference/cli
reference/emitters
reference/style-fields
reference/api-style
reference/api-anim
reference/shaders
reference/ast
```

```{toctree}
:caption: Internals
:hidden:

internals/architecture
internals/emitters
```
