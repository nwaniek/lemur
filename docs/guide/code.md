# Code

## Code blocks

`::` followed by a language starts a code block. The code is the indented body
below it, kept verbatim (even lines starting with `%%`):

```{lemur-example}
!slide A code block

:: python
	def sum_product(node, incoming):
	    msg = node.factor
	    for m in incoming:
	        msg = msg * m
	    return normalize(msg)
```

Highlighting happens at build time with Pygments, so every language Pygments
knows works: `:: cpp`, `:: rust`, `:: sh`, `:: haskell`, `:: tex`, and so on. The
colours come from the theme. A block without a language (`::` alone) is plain
monospace.

The body keeps its indentation relative to the first line, so nested code comes
out as written. Start a snippet at its shallowest line.

## Stepping through lines

A bracket after the language lists **highlight groups** separated by `|`. Each
group is one step: its lines are highlighted and the rest of the block dims.

```{lemur-example}
!slide Line by line

:: python[1|3-4|5]
	def sum_product(node, incoming):
	    msg = node.factor
	    for m in incoming:
	        msg = msg * m
	    return normalize(msg)
```

A group is a list of line numbers and ranges, such as `2`, `3-5` or `1,4`. The
steps count in the slide's normal order, so they interleave with bullets and
pauses around the block. To explain each group as it lights up, pair it with a
`!when`:

```lemur
:: python[2|3-4]
	...

!when<1>
	First we take the factor itself…
!when<2>
	…then multiply in every incoming message.
```

## Inline code

Backticks mark code within text: `` `np.argmax(wp)` ``. Nothing inside is
interpreted, including dollars, dashes and quotes.

## A label for a block

Like most blocks, a code block takes a `^ref`, so that `@ref` can point at it:

```lemur
:: python ^update
	x = x - eta * grad(x)
```
