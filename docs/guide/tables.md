# Tables

A table is a `!table` directive, a `!cols` line that declares the columns, an
optional `!caption`, and the rows indented below:

```{lemur-example}
!slide A table

!table Message schedule ^sched
!cols step[c], message, "value at $x=-1$"[r] | "value at $x=+1$"[r]
!caption Columns size to their content; cells may hold maths.

	1 , $\mu_{x_1\to f}$ , 0.5 | 0.5
	2 , $\mu_{f\to x_2}$ , ?   | ?
	---
	3 , marginal $p(x_2)$ , ? | ?
```

## Columns

`!cols` lists the column headers, separated by a punctuation character of your
choice. `,`, `;`, `|`, `&` and `/` all work, and one table may mix them:

```lemur
!cols Name, Age; Country | Notes
```

A header may carry an alignment in brackets: `[l]` left (the default), `[c]`
centred, `[r]` right. Header names consist of letters, digits and spaces. A
header containing punctuation (a comma, parentheses, maths) goes in double
quotes, and `\"` puts a quote inside quotes:

```lemur
!cols "Long header, with comma"[c], "Value ($\mu$)"[r]
```

## Rows

Each row is one line of the indented body, with cells split at the separators
declared in `!cols`, in the same order. So choose separators that don't occur
in your cells. If a row has a different number of cells than there are
columns, the build warns.

Between rows, a line of `---` draws a light rule and a line of `===` a strong
one. `\n` inside a cell breaks the line.

## No header row

`!noheader` drops the header row. `!cols` still defines the columns, their
separators and alignments; give bare alignments if there is nothing to name:

```{lemur-example}
!slide Without a header

!table
!cols [l], [r]
!noheader

	Alice , 30
	Bob   , 25
```

## Captions and references

`!caption` may run over several lines, as long as there is no blank line
inside it. A `^ref` on the `!table` line makes the table a target for `@ref`.
