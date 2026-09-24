# Writing slides

A lemur document is plain text. This guide walks through the language one topic
at a time, and every example has a live preview. The rules on this page apply
everywhere.

## Lines that start with something special

lemur keeps ordinary prose ordinary. A line only means something special when
it *starts* with one of a few markers:

| A line starting with | is |
|---|---|
| `!name` | a **directive**: a slide, a table, an image, a layout block, … |
| `::` | a **code** or **maths** block (`:: python`, `:: math`) |
| `#`, `##`, `###` | a section divider, or a heading within a slide |
| `-`, `*`, `+`, `1.` | a list item |
| `^key:` | a bibliography entry or a named link |
| `%%` | a comment, ignored |

Anything else is text. Paragraphs are separated by blank lines.

## One shape for every directive

Every directive has the same shape:

```lemur
!name[options]<overlay> text ^ref
```

- **`[options]`**: style classes, sizes, widths or line ranges. Examples:
  `!slide[.center] Title`, `!columns[60 40]`, `!gap[2em]`, `:: python[1|3-4]`.
- **`<overlay>`**: *when* to show it: `!when<2->`, `!layer<1>`, `+<3>`. See
  [Steps and overlays](steps.md).
- **text**: the human part: a title, a caption, a value.
- **`^ref`**: a label, so that `@ref` elsewhere can point here. See
  [References](references.md).

Both brackets attach to the directive **without a space**. That lets a title
start with `[` without being read as options.

## Indentation delimits blocks

Blocks that contain other content (a code block, `!columns`, an environment,
`!when`, the rows of a table) take an **indented body**, and a dedent ends it.
There are no end markers.

```lemur
!theorem Fixed point
	On a tree, sum-product converges to the exact marginals.

	:: math
		p(x) \propto \prod_{a \ni x} \mu_{a \to x}(x)

Back at the slide's own level.
```

The **first line of a body defines its indentation**: every later line must
start with exactly the same whitespace, and anything deeper is content (useful
for nested code). You choose tabs or spaces per block; no tab width is ever
assumed. A line that breaks the pattern is an error with a line number, not a
silent misparse.

## Comments

A line whose first non-blank characters are `%%` is ignored, even between the
rows of a table or the lines of a paragraph. The only exception is the body of
a code block, which is verbatim: `%%` is meaningful in Erlang and MATLAB. Write
`\%%` to start a line of text with a literal `%%`.

## The topics

- [Slides and structure](structure.md): slides, sections, headings, the title
  slide, configuration, speaker notes, multi-file talks
- [Text and formatting](text.md): emphasis, smart typography, escapes, styled
  spans, links
- [Lists](lists.md)
- [Steps and overlays](steps.md): the build-up of a slide
- [Maths](maths.md)
- [Annotations and arrows](annotations.md): explain equations and link ideas
- [Code](code.md)
- [Tables](tables.md)
- [Images](images.md)
- [Layout](layout.md): columns, stacks, styled blocks, spacing, slide classes
- [Environments](environments.md): theorem, proof, definition, …
- [References and citations](references.md)
