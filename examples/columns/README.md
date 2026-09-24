# Columns & stacks

`python3 lmr2svg.py examples/columns/deck.lmr -o columns.html`

- `!columns[3 2]` with `!column` children — weight-split sub-regions, each flows independently
- `!stack` with `!layer<spec>` children — overlaid, and one takes the place of the previous per step
