# Tables

`python3 lmr2svg.py examples/tables/deck.lmr -o tables.html`

- `!table Title` + `!cols a, b[r] | c[r]` + `!caption …`, then indented `,`/`|` rows
- columns are measured from content and the table centres as a block; `[c]`/`[r]` align; `---` / `===` are rules
