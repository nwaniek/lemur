# Mathematics

Inline and display maths, rendered to baked SVG outlines via LaTeX/dvisvgm.

`python3 lmr2svg.py examples/math/deck.lmr -o math.html`

- inline `$…$` sits on the text baseline; display `$$…$$` centres on its own line
- `\mk{name}{…}` names a sub-expression so `!annotate`/`!connect` can point at it
