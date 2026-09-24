# Display contract (v3)

The public interface between an **emitter** (renders slide DOM from some source
AST) and the **presenter** (the source-agnostic behavior core in
`lemur/assets/runtime.js`). Any emitter that produces this DOM + config, uses the token
vocabulary, and drives these hooks gets navigation, scaling, the step model,
transitions, print, and the slide overview for free. `lemur.emit.html` (the HTML
emitter behind `lmr2slides`) is the reference; any other emitter that produces a
DOM deck targets the same contract — the presenter never names a source
construct. (`lmr2svg` decks carry their own, self-contained player and are not
bound by this contract.)

The DOM is rendered at **build time** and present at load; the presenter only
drives it (it never builds slide DOM). This contract therefore spans three
versioned things: the **DOM structure** (§1), the **token vocabulary**
(`lemur/assets/tokens.css`, §1b), and the **hook API** (§7).

This is **contract version 3** (`LMR.contractVersion`). Renaming an attribute,
class, or token below, or changing a hook signature, is a breaking (major)
change.

## 1. DOM structure

The emitter renders, into a `.deck` element:

```
<div class="deck" data-design-w data-design-h data-transition data-step-transition>
  <section class="slide [role] [variant…]" id="…">
    <div class="stage">                      the fixed design box (scaled)
      <div class="layer-bg"></div>           background layer (swappable)
      <div class="stage-content"> … </div>   content layer (title + body)
      <svg class="arrow-layer">…</svg>        overlay layer (arrows; runtime-drawn)
      <div class="layer-chrome"> … </div>     chrome layer (header / logo / footer)
    </div>
  </section>
  …
</div>
```

**Slide layers** — the direct children of `.stage`, z-stacked back to front, each
a named, swappable subtree (the single scale transform on `.stage` scales them
together): `.layer-bg` (background — a theme replaces or layers over it),
`.stage-content` (the content), the `.arrow-layer` SVG (annotations/arrows, drawn
by the runtime), and `.layer-chrome` (header/logo/footer, one restyleable unit).

The presenter reads only:

- `.deck > .slide` — the ordered slides.
- each slide's `.stage` — the fixed design box it scales (and clones for print).
- `.stage-content` — the element the `push` transition moves (chrome stays put).

Everything else inside `.stage` is opaque: the presenter never inspects slide
content.

## 1b. Token vocabulary

`lemur/assets/tokens.css` declares a default for every `--lmr-*` token — the complete,
documented theming surface. Structural CSS references tokens with no inline
fallbacks; a theme's `theme.css` overrides only tokens (it is concatenated after
tokens.css and base.css, so it wins), and a per-slide variant may re-scope any
token (`.slide.dark { --lmr-bg:#111 }`). Renaming or removing a token is a
breaking change. Runtime-set variables (`--scale`, `--arrow-*`, `--hl`,
`--design-w/h`) are *not* theme tokens.

## 2. Deck config — attributes on `.deck`

| attribute | meaning |
|---|---|
| `data-design-w`, `data-design-h` | design box in px; the presenter fits it to the viewport |
| `data-transition` | across-slide: `none` \| `fade` \| `slide` \| `push` |
| `data-step-transition` | within-slide reveal: `none` \| `fade` \| `rise` |
| `data-progress="top"` \| `"bottom"` | show a thin progress bar at that edge (absent = off) |
| `data-print="eager"` | build print pages on load (else lazily, on Ctrl-P) |

The presenter sets `--scale` on `.deck` (and mirrors the design box as
`--design-w` / `--design-h`). When `data-progress` is present it creates a
`<div class="deck-progress" data-pos="…">` inside the deck and sets its
`transform: scaleX(f)` to the deck's fractional position across all
(slide, step) stops.

## 3. Step protocol — attributes the bridge puts on gated elements

The presenter's step model reads these; a bridge emits whichever it needs. All
step numbers are 1-based; step 0 is the base (nothing gated).

| attribute | behaviour | adds to the step count |
|---|---|---|
| `data-appear="n"` | hidden until step ≥ n, then stays (cumulative); presenter toggles `is-visible` | n |
| `data-when="<spec>"` | visible only while the step matches `<spec>` (may hide again); presenter toggles `is-visible` | largest number in the spec |
| `data-hl="n"` | gains `is-hl` from step n onward (cumulative); the bridge/theme colours `.is-hl` | n |

`<spec>` grammar (beamer-style, comma-separated terms): `n` (only n), `n-`
(from n), `-n` (up to n), `n-m` (n..m).

The presenter writes `data-step="s"` on each slide as it applies step s.

## 4. State classes — owned by the presenter

A bridge must **not** set these; it (or its theme CSS) styles the *reactions* to
them and the presenter never reads them back.

- Per slide (position / transition): `is-current`, `is-before`, `is-after`,
  `is-out`, `no-anim`.
- Per gated element: `is-visible`, `is-hl`.

## 5. Optional navigation UI

If the deck contains `<nav class="deck-nav">` with `<button class="deck-nav-prev">`
and `<button class="deck-nav-next">`, the presenter wires their clicks, toggles
`at-start` / `at-end` on the nav, and sets its `data-more` = `step` | `slide`.
Absent → keyboard, mouse-wheel (down = forward, up = back; throttled to one step
per notch, present mode only) and hash navigation still work.

## 6. Print

If a `.print-root` element exists, the presenter fills it with one
`<section class="print-page">` per cumulative step per slide, each wrapping a
frozen clone of that slide's `.stage` (hidden on screen, shown in `@media print`).

## 6b. Slide overview

The presenter builds and toggles a `.deck-overview` plane on demand: one
`<button class="overview-thumb">` per slide, each wrapping a frozen clone of the
slide's `.stage` at its **final** step (its end state). Two layouts on the same
nodes — `.is-grid` (a modal Slide-Sorter overlay, dims `.deck.is-gridded`) and
`.is-sidebar` (a docked rail; the deck shrinks via `.deck.is-docked` + a
`--sidebar-w` on `:root`). Keys: **`o`** toggles the grid, **`O`** (Shift+O) the
sidebar, `Esc` closes; a thumbnail carries the slide's variant/kind classes (so
per-slide CSS renders faithfully, like a print page). The sidebar's right edge is
a drag handle (`.deck-overview-resizer`) that resizes `--sidebar-w` (remembered in
`localStorage`). It is built like print pages (via the `beforeFreeze` hook), so it
costs the bridge nothing beyond the arrows it already draws for print.

## 7. JS hook API — the plugin surface

The runtime is a lean source-agnostic **core** (the `Deck`: state, navigation,
scaling, transitions, the step model, hash) plus **plugins** that attach *only*
through the surface below. Everything else is a plugin: the source-specific lemur
bridge (arrows, code highlighting, math) **and** the source-agnostic presenter
features — the **overview** (`createOverview`) and **print** (`createPrint`) —
which the core no longer contains. The overview is the reference for a plugin
that owns keys, a modal mode, and a docked panel without the core knowing any of
it.

- `deck.on(event, fn)` — subscribe. Events:
  - `show(i)` — slide `i` became current (measure per-slide things; the overview
    marks its current thumbnail).
  - `step(root, s)` — step `s` applied to `root` (a live slide **or** a frozen
    clone); layer per-step DOM here so screen, print and overview stay identical.
  - `layout()` — the viewport resized (re-measure layout-dependent things).
  - `beforeFreeze()` — before *any* frozen projection (print pages, overview
    thumbnails) is built; finalise every slide (e.g. draw all arrows).
  - `start()` — the window listeners are wired and `deck.signal` is live (a
    plugin adds its own signal-scoped listeners here, e.g. print's `beforeprint`).
  - `ready()` — async resources (`whenReady` promises + fonts) have settled.
- `deck.addStepCounter(fn)` — `fn(slide) → int`, a plugin's extra step count,
  folded into the slide's total.
- `deck.addKeyHandler(fn)` — `fn(event) → handled?`; runs before the core's own
  nav keys, so a plugin claims keys without the core knowing them.
- `deck.whenReady(promise)` — awaited before `ready` fires.
- `deck.applyState(root, s)` — apply the core step state to a root, then fire
  `step` (used on-screen and on frozen clones).
- `deck.recountSteps()` — recompute step counts after a plugin changes the DOM.
- Levers a plugin sets on the core: `deck.viewportInset` (px a docked panel
  reserves; the scale fits what's left), `deck.wheelNav` (clear to suspend
  wheel-nav), `deck.signal` (the listener `AbortController` signal).

## Versioning

`LMR.contractVersion` is `3`. A different source's emitter should check it and
refuse a version it does not understand, rather than mis-driving the presenter.
