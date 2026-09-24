# References and citations

lemur borrows its reference syntax from pointers in Pascal: `^` *declares* a
label and `@` *dereferences* it.

## Labels and cross-references

Attach `^name` to anything that can be referred to: a slide or section, a
heading, a table, an image, a code or maths block, an environment, an
animation. Then `@name` anywhere in the talk links to it and shows its label,
much like LaTeX's `\ref`. `[text]@name` uses your own wording:

```{lemur-example}
!slide Definitions ^defs

A factor graph factorises a joint distribution; we build on this in @results.

!slide Results ^results

By the argument in @defs, sum-product is exact on trees.
[As shown before]@defs, the graph must be a tree.
```

A name uses letters, digits, `_` and `-`, so punctuation right after it ends
it: `see @defs.` refers to `defs`. A reference to a label that doesn't exist is
reported by the build.

## Bibliography and citations

A line of the form `^key: entry` defines a bibliography entry. Entries are
numbered in the order they are defined, and the entries are listed where they
appear. `@key` cites one entry, and `@(key1, key2)` several:

```{lemur-example}
:step: last

!slide Results

Sum-product is exact on trees @kschischang2001, an idea that goes back to
belief propagation @pearl1988; see also @(pearl1988, kschischang2001).

!slide Bibliography

^kschischang2001: Kschischang, Frey, Loeliger (2001). Factor graphs and the sum-product algorithm. IEEE Trans. Inf. Theory 47(2).
^pearl1988: Pearl (1988). Probabilistic Reasoning in Intelligent Systems. Morgan Kaufmann.
```

`[text]@(key1, key2)` replaces the citation marker with your own words, as
`\cite` does with an optional argument. A citation may follow a word without a
space (`Kording@jonas2010`), while an e-mail address (`me@host.tld`) is left
alone.

## Links

Angle brackets turn a URL or e-mail address into a link: `<https://example.org>`.
`[text]@(https://…)` links your own words. A line `^name: <url>` defines a
**named link** that shows nothing by itself; `[the course page]@site` then
links to it:

```lemur
^site: <https://example.org/course>

All material is on [the course page]@site.
```

For a key with unusual characters, the explicit form `@(key)` always works.
