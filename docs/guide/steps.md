# Steps and overlays

A slide is built up in **steps**. Step 0 is the slide as it first appears.
Every keypress advances to the next step, until the slide is complete and the
next keypress moves on to the following slide. One integer per slide drives
everything that appears, changes or disappears:

- `!pause` and `+` list items
- inline runs and blocks with an overlay (`[text]<2->`, `!when<2->`)
- stacked layers (`!stack` / `!layer`)
- the layers of a multi-source image
- the highlight groups of a code block
- the lines of `!annotate` and `!connect`

These all draw from the same counter, in reading order, so they interleave
naturally. When everything on a slide has been revealed, the slide's
[animations](../figures/animations.md) and [shaders](../figures/shaders.md) take
over: each further keypress plays the next animation beat or shader step.

## `!pause`

Everything after a `!pause` appears together on the next keypress:

```{lemur-example}
!slide A pause

First, the question: why does this converge?

!pause

Then, the answer: it is a contraction.
```

## `+` items

A `+` list item takes a step of its own (see [Lists](lists.md)):

```{lemur-example}
!slide Items

+ one
+ two
+ three
```

## Overlay specs

An **overlay spec** in angle brackets says exactly on which steps something is
visible, as with Beamer's overlays in LaTeX. A spec is a comma-separated list
of terms:

| Term | Visible |
|---|---|
| `<n>` | only on step *n* |
| `<n->` | from step *n* on |
| `<-n>` | up to step *n* |
| `<n-m>` | from step *n* to step *m* |
| `<1,3->` | on step 1, and from step 3 on |

Something with a bounded spec disappears again. It still reserves its space
while hidden, so revealing or hiding it never shifts the rest of the slide.

**On a list item**, the spec goes right after the marker: `+<2->`, `-<3>`.

**On an inline run**, put the text in brackets. A word or phrase can then appear
in the middle of a sentence:

```{lemur-example}
!slide Inline reveals

The answer is [surprisingly]<1-> simple: [it is a contraction]<2->.
```

**On a block of anything**, use `!when<spec>` with an indented body:

```{lemur-example}
!slide Blocks

Two lines of maths:

:: math
	\theta \leftarrow \max_i f(n_i, t)

!when<1->
	and two lines of code:

	:: python
		winner = np.argmax(wp)

!when<2>
	(this remark is shown on step 2 only)
```

`!when` blocks nest, and the inner spec applies within the outer one.

## Relative steps

Numbers are brittle: insert a step early on a slide and every later number is
off by one. Relative specs avoid numbering altogether:

- `<+->` shows from the **next** step on, like a `+` item, for any content;
- `<+>` shows **only during** the next step.

```{lemur-example}
!slide No numbers

Reveal [this]<+->, then [that]<+->, then [only briefly this]<+>.

!when<+->
	A whole block, on the following step.
```

The parser numbers relative steps in reading order, so you can reorder and copy
content freely.

## Stacks: things that take each other's place

A `!stack` holds `!layer`s that **overlap in one spot**, so each takes the place
of the previous one instead of being stacked below it. Every layer needs an
explicit overlay. The stack reserves room for its tallest layer, so nothing
below it moves as layers swap.

```{lemur-example}
!slide Stacked

!stack
	!layer<0>
		- a variable sends the product of its **incoming** messages
	!layer<1>
		- a factor weighs by its **local factor** and marginalises
	!layer<2->
		- on trees this is **exact**; on loopy graphs it iterates

This line stays put underneath as the point above swaps.
```

A layer can hold anything, including a whole `!columns` layout. That makes a
stack the way to switch a slide's layout on a keypress (see
[Layout](layout.md)).

## How steps appear

The deck's step transition (`!transition <across> <step>`) sets how new content
arrives: `none`, `fade` (the default) or `rise`. See
[Slides and structure](structure.md#the-title-slide-and-configuration).
