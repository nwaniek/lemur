# Annotations and arrows

A talk explains. lemur lets you point at things by **name** rather than by
position: name a part of a formula or of a sentence, then colour it, label it
or connect it to something else, one step at a time. lemur places the labels
and arrows from the typeset layout, so they follow when you edit the slide.

## Naming things: marks

A **mark** is a named piece of content:

- in maths: `\mk{name}{…}`, e.g. `$\mk{lik}{p(x \mid \theta)}$`;
- in text: `[…]^name`, e.g. `the [important part]^key`.

A name uses letters, digits, `_` and `-`. A mark looks exactly like the
unmarked content until you do something with it.

## `!annotate`: colour and label

Each line of an `!annotate` block is `name[style]: label`, and each line is one
step. On that keypress, the named part takes a colour, the label appears, and
an arrow is drawn from the label to the part:

```{lemur-example}
!slide Annotate an equation

:: math
	\mu_{a \to x}(x) = \mk{sum}{\sum_{x_{\partial a}\setminus\{x\}}}
		\mk{fac}{f_a(x_{\partial a})} \mk{prod}{\prod_{y} \mu_{y\to a}(y)}

!annotate
	prod: collect the incoming messages
	fac[#7a4b94]: weigh by the local factor
	sum[#b0672f]: marginalise out everything except $x$
```

Colours accumulate, so the formula fills with colour as you explain it. Without
a colour, a palette cycles. Labels may contain inline maths. Keep them short,
because they do not wrap.

### Emphasis without an arrow

A line **without label text** just restyles the mark on that step. The bracket
takes a colour and the styles `.bold`, `.italic` and `.underline`. This works
nicely on text you are talking through:

```{lemur-example}
:step: last

!slide Emphasis on a keypress

- convergence is the [interesting question]^q on loopy graphs
- the schedule is [surprisingly subtle]^sched
- and the whole iteration is [asynchronous by nature]^async

!annotate
	q[#c0392b .bold]:
	sched[.bold]:
	async[#2e5e6e .italic]:
```

## `!connect`: arrows between two marks

Where `!annotate` points a label at a mark, `!connect` draws an arrow **between
two marks**. Use it to link a question to its answer, a symbol to its
definition, or a cause to its effect. Each line is `from ARROW to [style]`, and
each line is one step:

```{lemur-example}
:step: last

!slide[.center .middle] What is our field about?

[what is computed]^q1? · [how is it feasible]^q2?

!gap[1.5em]

[theory of computation]^a1<1-> · [compositional representations]^a2<2->

!connect
	q1 -> a1  [#c0392b]
	q2 -> a2  [#2e5e6e]
```

| Arrow | Meaning |
|---|---|
| `a -> b` | from *a* to *b* |
| `a <- b` | from *b* to *a* |
| `a <-> b` | heads at both ends |
| `a -- b` | a plain line |

The bracket takes a colour and the line styles `.dashed`, `.thin` and `.thick`.
The connector attaches to the facing edges of the two marks. A mark that
appears on a later step (as the answers do above, with `<1->`) brings its arrow
along when it appears.

## Groups: one name, several places

Using a name **more than once** on a slide makes a **group**. The occurrences
share one colour, and a label's arrow fans out to each of them. This is useful
when the same quantity appears twice, say once compactly and once expanded:

```{lemur-example}
:step: last

!slide A group

:: math
	\mk{Z}{Z} = \sum_x \prod_a f_a(x_{\partial a})
	\qquad\Rightarrow\qquad p(x) = \frac{1}{\mk{Z}{Z}} \prod_a f_a(x_{\partial a})

!annotate
	Z[#c0392b]: the partition function
```

A connector whose end is a group pairs each occurrence with its nearest
counterpart. Since reusing a name is usually a typo, the parser warns about it.
The warning is harmless when the reuse is deliberate.
