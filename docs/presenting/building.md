# Building and diagnostics

## The build

```console
$ lmr2svg talk.lmr -o talk.html
wrote talk.html  (6912 placements, 423 distinct outlines)
```

The first build of a deck typesets every formula with LaTeX, which takes a
while for a long talk. LaTeX results are cached (see
[installation](../getting-started/installation.md#the-typesetting-cache)), so
later builds only typeset what changed. `!plot` scripts and `!anim` modules run
on every build.

Without `-o`, the output is written next to the input as `<name>.svg.html`.

## Writing with live reload

```console
$ lmr2svg talk.lmr --watch
```

`--watch` builds the deck, serves it on `http://127.0.0.1:8000` (change the port
with `-p`), and opens a browser (unless `--no-open`). It then rebuilds whenever
you save a file in the deck's folder: a `.lmr` file (including included files),
its `style.py`, a `!plot` script or an `!anim` module, a shader or an image. The
page reloads itself and stays on the slide you were looking at.

To work on one animation, [`lmranim`](../figures/viewer.md) is quicker: it
shows just that animation with a timeline and rebuilds only it.

## Diagnostics

A problem in one slide never stops the build; lemur reports it and carries on.
Every message names the slide:

```text
lemur emit-svg: warning: slide 3 ('Contour of a scalar field'): content overflows the slide body by 39px
```

| Reported | What you see in the deck |
|---|---|
| a LaTeX error in a formula | the formula's source in red |
| a missing image or title image | a placeholder |
| content taller than the slide | the overflowing content (fix: shorten, split, or use columns) |
| an equation wider than its column | the equation, scaled down to fit |
| a table or code block wider than its column | the block as it is |
| a reference or citation that does not resolve | the marker, unlinked |
| a table row with the wrong number of cells | the row as split |
| an unknown theme | the default theme |
| a mark name used twice on a slide | the marks, grouped (often intended) |
| an `!anim` or `!plot` script that raises an error | an empty space where the figure would be; the error is in the message |

Structural errors stop the build with a file name and line number, because the
document cannot be understood past them. Examples are inconsistent
indentation, an unknown directive, a block without its body (such as `!notes`
with nothing indented below it), and a circular `!include`:

```text
lemur emit-svg: talk.lmr:42: unknown directive '!colums'
```

## Strict builds

```console
$ lmr2svg talk.lmr --strict
```

`--strict` turns every warning into a failure: the build exits with status 3 if
anything was reported. Use it in CI, or before a talk, to be sure every slide
is clean.

## Output quality

Every glyph and formula becomes a vector outline. `--quality` sets how many
decimals the outlines keep: `draft` and `low` make smaller files, while `high`
and `max` suit print and deep zoom. On screen the difference is subtle. The
default is `medium`.

## Designing with wireframes

```console
$ lmr2svg talk.lmr --wireframe
```

`--wireframe` writes `talk.wireframe.html`, which draws the design's title and
body regions as labelled boxes. Use it when you move regions in a
[`style.py`](../design/style.md).
