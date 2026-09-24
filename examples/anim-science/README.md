# Animated scientific figures

`python3 lmr2svg.py examples/anim-science/deck.lmr -o anim-science.html`

Three `!anim` figures built with `lemur.anim`, each one beat = one slide step:

- **`lorenz.py`** — the Lorenz attractor integrated and drawn on *over time*
  (`Create` traces the trajectory), viewed in 3D via `View`. Tracing is one
  draw-range track; orbiting would be cheap too (the player projects the 3-D
  points, the deck only stores the camera angles).
- **`integral.py`** — a 2-D plot (a top-down `View`: `axes`/`plot`/`point`/`area`),
  the curve drawn on, then the area under it **sweeps in** to x → 4 (an updater rebuilds the filled
  region each frame, driven by a `ValueTracker`).
- **`wave.py`** — the classic **sine from the unit circle**: a rotating radius
  and dot, a connector, and the sine traced out as the angle advances.

Pattern to reuse: drive geometry from a `ValueTracker` in an `add_updater`, then
`self.play(tracker.animate.set_value(...))` — the changing shape bakes into the
morph tracks the runtime plays. (See also `animation3d/` for `View`.)
