# Bundled fonts (for deterministic, cross-machine layout)

lemur lays every slide out in a fixed design box and then scales it uniformly, so
the layout is only reproducible if the *font metrics* are identical everywhere.
These fonts are therefore vendored and shipped inside each deck (copied to
`<deck>/fonts/` by `copy_fonts` in `lemur.slides`, declared via `@font-face` in
`base.css`), so a slide wraps and sizes the same on every machine and browser
(this is what fixed the Safari overflow / per-machine size drift).

All are `latin` subset and **SIL Open Font License 1.1** (freely
redistributable); their `OFL-*.txt` ship alongside. The first three are
**variable** (a single file per family covers the whole weight axis — heading
weight 650 and body 400/700 all resolve exactly, no browser faux-bold). Libre
Baskerville is **static**: three separate weights (400, 400-italic, 700), and it
has *no* bold-italic face, so bold+italic serif text falls back to a synthesized
slant.

| family | files | source (jsDelivr / Fontsource) | version |
|---|---|---|---|
| Source Sans 3 (sans — text, headings) | `source-sans-3-{normal,italic}.woff2` | `@fontsource-variable/source-sans-3` | 5.2.9 |
| Source Serif 4 (serif — optional) | `source-serif-4-{normal,italic}.woff2` | `@fontsource-variable/source-serif-4` | 5.2.9 |
| JetBrains Mono (mono — code) | `jetbrains-mono-{normal,italic}.woff2` | `@fontsource-variable/jetbrains-mono` | 5.2.8 |
| Libre Baskerville (serif — journal default) | `libre-baskerville-{400-normal,400-italic,700-normal}.woff2` | `@fontsource/libre-baskerville` | 5.2.10 |

To refresh a **variable** font, re-download from
`https://cdn.jsdelivr.net/npm/@fontsource-variable/<family>@<version>/files/<family>-latin-wght-<style>.woff2`;
for **static** Libre Baskerville, from
`https://cdn.jsdelivr.net/fontsource/fonts/libre-baskerville@<version>/latin-<weight>-<style>.woff2`.
Update the versions above.
