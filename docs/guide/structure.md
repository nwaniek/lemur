# Slides and structure

## Slides

`!slide Title` starts a slide. Everything up to the next `!slide` (or section)
belongs to it. The title is optional, and it may contain inline markup and
maths.

```{lemur-example}
!slide Bayes' rule, $p(\theta \mid x)$ ^bayes

The posterior is proportional to the likelihood times the prior.
```

A `^ref` after the title labels the slide, so that `@bayes` anywhere else links
to it (see [References](references.md)).

## Sections

A line starting with a single `#` is a **section divider**: a slide of its own
with a large, centred title. Any content after it is centred below the title.

```{lemur-example}
# Part II: Inference ^part2

From models to algorithms.
```

## Headings within a slide

Inside a slide, `##` and `###` are headings. They structure a busy slide
without starting a new one.

```{lemur-example}
!slide Two regimes

## Small step sizes
Stable, but slow.

## Large step sizes
Fast, until they overshoot.
```

## The title slide and configuration

Directives placed **before the first slide** configure the deck. The first five
make the title slide (the *cover*), which is shown before the first slide:

```{lemur-example}
!title      Message Passing on Graphs
!subtitle   From factor graphs to distributed algorithms
!author     R. Example
!institute  Summer School 2026
!date       July 2026
```

| Directive | Effect |
|---|---|
| `!title`, `!subtitle` | the talk's title (also the default footer text) and a subtitle |
| `!author`, `!institute`, `!date` | the byline of the title slide |
| `!titleimage path` | an image above the title on the title slide |
| `!logo path` | a logo on every content slide |
| `!header text` | a running header on content slides |
| `!footer text` | the footer text (default: the title) |
| `!slidenumbers on\|off` | slide numbers in the footer (default: on) |
| `!progress top\|bottom` | a thin progress bar along that edge |
| `!madewith` | a small "made with lemur" mark with the lemur logo, bottom-left on the title slide |
| `!theme name` | the design: see [Themes](../design/themes.md) |
| `!aspect 16:9\|4:3` | the slide format (1920×1080 or 1440×1080) |
| `!transition across [step]` | how slides change (`none`, `fade`, `slide`, `push`) and how steps reveal (`none`, `fade`, `rise`) |

About the transitions:
- The across-slide transition runs when moving between slides. `slide` moves
  the whole slide; `push` moves only the content, so the header and footer stay
  in place.
- The step transition runs when content appears within a slide. `rise` lifts
  each new item in from below.

## Per-slide classes

Options in brackets after `!slide` (or `#`) give the slide **classes**:

```{lemur-example}
!slide[.center .middle] The one idea to remember

**Local computations, passed along edges.**
```

These classes are built in:

| Class | Effect |
|---|---|
| `.center` | centre the body horizontally |
| `.middle` | centre the body vertically in the space below the title |
| `.plain` | no header, footer or logo |
| `.fill` | no padding around the content |
| `.dark` | a dark variant of the theme for this slide (dark ground, light ink) |

Any other class is for a theme or a [template](../design/templates.md): a
`style.py` can register a template under a name, and `!slide[.name]` then draws
that slide with it.

## Speaker notes

`!notes` holds notes for the speaker. They belong to the slide but are never
shown on it.

```lemur
!slide Why graphical models?

Many inference problems factorise.

!notes
	Ask who has seen belief propagation before; calibrate the pace.
```

## Multi-file talks

`!include path.lmr`, alone on a line, inserts another file as if its text were
written there. Paths are relative to the including file, includes may nest, and
a cycle is reported as an error. A course is typically a `master.lmr` with the
configuration and one file per chapter:

```lemur
%% master.lmr
!title   Message Passing on Graphs
!author  R. Example
!theme   journal

!include 00_intro.lmr
!include 10_factor_graphs.lmr
!include 20_inference.lmr
```

References work across files, so `@sum_product` in the introduction can point
to a slide in chapter 2. Build the master file:

```console
$ lmr2svg master.lmr -o course.html
```
