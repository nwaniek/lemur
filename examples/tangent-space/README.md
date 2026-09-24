# The tangent space (a short lecture)

`python3 lmr2svg.py examples/tangent-space/deck.lmr -o tangent-space.html`

Twelve slides on the tangent space of a Riemannian manifold, told on a **dome**
(the upper half of a sphere) in a dark, 3Blue1Brown-flavoured look. Five
`!anim`s carry the story; the slides between them hold the definitions, with
`!annotate` arrows, `!definition` / `!theorem` boxes and step reveals.

- **`world.py`** — the dome draws itself while the camera swings round; a point
  `p` appears and an "ant" walks a geodesic through it. Its velocity `γ'(0)` then
  rides along and never leaves the surface's tangent plane.
- **`plane.py`** — three curves through `p`, their velocities, and the plane they
  all lie in: `T_pM`. The camera swings round until the plane is edge-on — it
  touches the dome at `p` and nowhere else.
- **`logmap.py`** — `log_p`: the geodesic to `q` unrolls into a straight arrow in
  the plane, keeping its length. Then a geodesic circle and its spokes unroll —
  the spokes keep their length, the rim has to stretch (`2πR sin(r/R) < 2πr`).
- **`wrap.py`** — `exp_p` shrink-wraps a polar grid from `T_pM` onto the dome
  (straight lines through `p` become geodesics), an orbit to admire it, and
  `log_p` unwraps it again.
- **`bundle.py`** — `p` travels across the dome carrying its plane and a frame
  `(e1, e2)`, leaving tilted ghost planes behind: the tangent bundle.

`dome.py` holds the shared geometry (the exponential and logarithm maps of the
sphere, a tangent frame, and helpers for shapes that are re-projected every
frame while points move and the camera orbits). The trick used throughout: a
`ValueTracker` `lam` blends each point between its place on the dome, `exp_p(v)`,
and in the plane, `p + v`. Animating `lam` rolls things flat or wraps them up.
