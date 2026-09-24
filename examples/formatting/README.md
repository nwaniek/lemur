# Formatting & typography

Inline styling and lemurs smart-typography pass.

`python3 lmr2svg.py examples/formatting/deck.lmr -o formatting.html`

- `**bold**`, `__italic__`, `~~strike~~`, `++underline++` (and `.bold`/`.italic`/… class fallbacks)
- spans: `[text]{#colour}`, `[text]{bg:#tint}`, `[text]{.class}`
- smart typography (parser-level): `--`→en dash, `---`→em dash, `...`→ellipsis, curly quotes
- `!style[.frame bg:…]` — a rounded, tinted panel around a whole block
