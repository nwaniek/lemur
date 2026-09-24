# Annotations & connectors

`python3 lmr2svg.py examples/annotations/deck.lmr -o annotations.html`

- name a mark with `[text]^name` (prose) or `\mk{name}{…}` (maths)
- `!annotate` colours a mark and, if given a label, draws a straight arrow to it: `name[#colour]: label`
- `!connect` draws a (curved) arrow between two marks: `a -> b  [#colour]`
- arrows use the *real* build-time glyph boxes — no runtime measurement
