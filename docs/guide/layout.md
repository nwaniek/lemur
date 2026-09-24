# Layout

Slide content flows from top to bottom in the body area below the title. A few
containers arrange it differently. Each is an indented block ended by a dedent,
and they nest freely inside one another.

## Columns

`!columns` splits the slide into side-by-side columns. Each `!column` holds
ordinary lemur, indented beneath it:

```{lemur-example}
!slide Two columns

!columns[60 40]
	!column
		The main argument, 60% of the width. Any lemur works here: lists,
		maths such as $\nabla \cdot \mathbf{E} = \rho/\varepsilon_0$, pauses.

		- a point
		- another
	!column[.center]
		An aside, 40% wide, centred vertically.
```

In the `!columns[…]` bracket, numbers are relative column widths: `[60 40]`,
`[3 2]` and `[1 1 1]` all work. Leave them out for equal columns. Other tokens
style the container, as with [styled blocks](#styled-blocks). `!column[.center]`
and `!column[.bottom]` align a column vertically (top is the default).

Only `!column`s may appear directly inside `!columns`. A stray line there is an
error.

**Steps flow across columns** in reading order. A `!pause` in the left column
therefore also holds back everything in the right column:

```{lemur-example}
!slide Steps across columns

!columns[50 50]
	!column
		First the setup.

		!pause
		Then the twist.
	!column
		And only then this column.
```

## Stacks

A `!stack` places its `!layer`s **on top of each other**, each shown on the
steps its overlay names. It is covered in [Steps and overlays](steps.md#stacks-things-that-take-each-others-place).
Since a layer can contain columns, a stack can switch the whole layout of a
slide on a keypress:

```{lemur-example}
!slide Switching layouts

!stack
	!layer<0>
		!columns[50 50]
			!column
				First layout: left
			!column
				right
	!layer<1->
		!columns[30 70]
			!column
				Second layout
			!column
				with a much wider right column
```

## Styled blocks

`!style[…]` styles a whole block of content. It uses the same vocabulary as
[styled spans](text.md#styled-spans), plus two built-in block classes: `.frame`
draws a rounded box and `.center` centres the content.

```{lemur-example}
!slide A framed panel

!style[.center .frame bg:#f5f7ff]
	A centred, framed panel on a tinted background.

	It can hold anything, including maths: $E = mc^2$.
```

## Vertical space

`!gap` adds vertical space between blocks:

- `!gap` alone adds a default gap;
- `!gap[2em]` adds a fixed amount (`px`, `em`, `rem`, `%`, … work too);
- `!gap[fill]` grows, pushing what follows towards the bottom. Several `fill`
  gaps share the free space.

```{lemur-example}
!slide Take-home message

Most of the slide.

!gap[fill]

**The one line that matters**, at the bottom.
```

## Whole-slide layout

The slide classes `.center` and `.middle` centre the body horizontally and
vertically; `.plain` removes the header and footer; `.fill` removes the padding.
See [Slides and structure](structure.md#per-slide-classes).

For entirely different slide designs, such as a cover with a photo or a slide
with a coloured band, write a [template](../design/templates.md).
