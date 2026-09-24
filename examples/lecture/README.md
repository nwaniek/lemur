# Lecture — a full multi-file course

A realistic, longer deck: *Message Passing on Graphs*. It's the reference for a
real talk and exercises most of the language at once — sections, maths,
annotations, columns, stacks, tables, figures, code, environments, references,
transitions, and speaker `!notes`.

`master.lmr` is the entry point; it sets the deck metadata and `!include`s the
chapters in order:

```
master.lmr
  00_intro.lmr        10_factor_graphs.lmr   20_features.lmr
  30_connectors.lmr   40_timing.lmr          50_lists.lmr
  60_styling.lmr      90_references.lmr
figs/                 (title hero, factor-graph layers, logo)
```

## Build

```sh
python3 lmr2svg.py examples/lecture/master.lmr -o lecture.html
```

Uses the default (`clean`) theme; try `--theme dark` or `--theme journal`, or
`lmr2svg --separate-images` to ship the figures alongside instead of embedding
them. This is a good deck to read top to bottom to see how the pieces combine in
a real talk.
