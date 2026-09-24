# Transitions & reveals

`python3 lmr2svg.py examples/transitions/deck.lmr -o transitions.html`

- `!transition <across> <step>` — across `none|fade|slide|push`, step `none|fade|rise` (a master/theme default is overridden by this)
- `+` / `!pause` reveal content step by step; `!gap[2em]` / `!gap[fill]` add space
- `!slide[.center .middle .plain .dark]` — layout/chrome variant modifiers
