# Parallel transport (a short lecture)

`python3 lmr2svg.py examples/parallel-transport/deck.lmr -o parallel-transport.html`

A six-slide visual lecture built almost entirely from `lemur.anim` — a showcase
of what a `.lmr` deck can do:

- **`flat.py`** — in the plane, a vector carried around a loop returns unchanged
  (a top-down `View`, i.e. a 2D plot).
- **`tangent.py`** — a wireframe **sphere** with the **tangent plane** `T_pS` and
  a tangent vector at a point (3D via `View`, a semi-transparent `polygon`).
- **`holonomy.py`** — the punchline: parallel-transport a vector around a
  spherical triangle and it comes back **rotated 90°** (the transported vector vs.
  a ghost of the original), with the angle labelled.
- `deck.lmr` ties them together with text + `$…$` maths (Gauss–Bonnet).

Shared maths (rotations, great-circle arcs, `transport_along`, a re-projecting
`vector` arrow, the `sphere`) lives in **`geom.py`**, imported by each `!anim`
module — sibling imports work because the emitter puts the deck's directory on
`sys.path` while running an `!anim`. The whole deck bakes to one self-contained
~0.6 MB HTML.
