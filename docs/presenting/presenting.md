# Presenting

A deck built by `lmr2svg` is one HTML file. Present it from any browser, on any
machine, with no network. Copy it to a USB stick, attach it to an e-mail, or put
it on a web page.

## Keys

| Key | Action |
|---|---|
| → Space PageDown, a click, wheel down | next step |
| ← PageUp, wheel up | previous step |
| ↓ / ↑ | next / previous slide |
| Home / End | first slide / end of the talk |
| `o` | overview grid of all slides; arrows and Enter (or a click) jump, Esc closes |
| `O` | a thumbnail sidebar next to the live slide |
| `m` | switch the soundtrack of a [shader](../figures/shaders.md) slide on and off |

Presenter remotes send PageDown/PageUp or the arrow keys, so they work as they
are. Press F11 (or your browser's full-screen key) for full screen.

## Addresses

The address bar tracks `#/<slide>/<step>`, for example `talk.html#/12/3`. A
reload returns to the same place. You can also send a link to a particular
moment of a talk, or open a deck at a slide to rehearse it.

## Screens and aspect ratios

A slide is laid out once, in its fixed design box, and scaled as a whole to fit
the window. On a screen with another aspect ratio, bars appear at the sides or
the top; nothing is stretched or reflowed. Choose the deck's format with
`!aspect 16:9` (the default) or `!aspect 4:3` to match the projector.

## Printing and PDF handouts

The browser's print dialog prints one page per slide, each in its final state:
everything revealed, animations at their end, shader slides with their last
frame. Choose *Save as PDF* there for a handout. Content that disappears during
a slide (a bounded overlay such as `<2>`) is left out of the printed page.

## Sharing

- A deck is self-contained: fonts, maths and images are all embedded. For very
  large photo-heavy decks, `--separate-images` writes a folder instead, with the
  deck's `index.html` and an `images/` folder. Share the whole folder.
- Stepping, transitions, animations and shaders run in the browser's
  JavaScript, which browsers enable by default. `!compute` slides also need
  WebGPU (see [Compute shaders](../figures/compute.md)).
- Speaker notes (`!notes`) are not included in what the audience sees.
