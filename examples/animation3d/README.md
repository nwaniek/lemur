# 3D animation

`python3 lmr2svg.py examples/animation3d/deck.lmr -o animation3d.html`

- `lemur.anim.View` is **3D projected by the player**: 3D curves/axes ship
  their world-space points once, plus the camera angles over time; the deck's
  runtime projects them every frame. Orbiting the camera (`sp.reorient(elev=…,
  azim=…)`) is therefore a tiny angle track, however much geometry is on screen.
  The still frame (print, no JavaScript) is projected at build time with the
  same maths (`lemur/anim/world.py` ↔ `lemur/assets/svg/world.js`).
- The example shows the complex exponential `e^{it}`: straight down the z-axis it
  is the unit circle in the complex plane; tilt the camera and it unwinds into a
  helix — an oscillation along z.
- `View` primitives: `parametric(fn, t0, t1)`, `curve(points)`, `line(a, b)`,
  `axes(x, y, z)`, `label(text, anchor)`; the view is two animatable angles, so a
  camera move is an ordinary `self.play`.
