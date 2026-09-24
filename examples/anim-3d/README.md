# 3D building blocks

`python3 lmr2svg.py examples/anim-3d/deck.lmr -o anim-3d.html`

Reusable pieces for scientific 3D, all in `lemur.anim`:

- **A view = a camera + a viewport.** `View(azim, elev, scale, viewport=(cx,
  cy, w, h))` draws into that rect and clips to it — so the *same* plotting code
  makes a main plot or an inset just by changing the viewport (a "virtual
  viewport"). A 2-D plot is simply the top-down case (`elev=90`). No inset vs.
  normal distinction.
- **`View.axes(x, y, z, numbers=True)`** — each of `x`/`y`/`z` is a half-length
  or a `(lo, hi, step)` range; with a step you get tick marks, and `numbers` adds
  numeric labels — a real coordinate system, clipped inside its viewport.
- **2-D plots are the same thing** — `View(elev=90).fit(x_range, y_range)` is a
  top-down view; `plot(fn, x0, x1)`, `point(x, y)`, `area(fn, x0, x1)` work in data
  coordinates (out-of-range is clipped by the viewport). `static=True` makes curves
  `Transform`-able. There is no separate 2-D plot type — one space for everything.
- **`View.surface(fn, u_range, v_range)`** — a wireframe surface; `surface.py`
  orbits a decaying ripple.
- **`View.trace_dot(points, progress, by=…)`** and **`View.rate(points)`** —
  a marker riding a curve; share one `progress` (and per-view `rate` on `Create`)
  to draw the trajectory and move the **same 3-D point in every view at once**.
  `lorenz_views.py`: one attractor, a main 3-D view + top/front/side insets.
- **Perspective** — `View(perspective=distance)` divides by depth, so nearer
  things look bigger. `projection.py` puts the *same* row of cubes on a grid in an
  orthographic and a perspective viewport side by side (the far cubes shrink and
  the grid lines converge).
- **Solids + z-sorting** — `View.polygon`, `View.solid(vertices, faces)` and
  `View.box(center, size)` build filled faces, painter-sorted by depth so nearer
  ones cover farther ones (correct for a still camera). `bars3d.py` is a perspective
  3-D bar chart. *(Rotating solids would need per-frame re-sorting, which a baked
  scene can't do — orbit wireframes, keep solids still.)*
- **Moving 3-D things** — `View.curve_fn(points_fn)` is a polyline whose 3-D
  points are recomputed each frame (it blends, unrolls, follows a tracker);
  `View.dot(where)` and `View.pin(shape, where, offset=…)` pin a dot, a label or
  any 2-D shape to a 3-D point (or a callable). Set `view.occluder = {"c": …,
  "R": …, "cap": z|None}` (a sphere, or a dome) and `curve_fn(…, rule="vis"|"hid")`
  draws only the part in front / behind it, `pin(…, rule="hide"|"ghost")` hides
  or dims what goes behind — decided by the player each frame, for the current
  camera. `lemur.anim.illustrate` builds its paper-figure style on these.
- **What ships** — a `View` shape stores its 3-D points once (or as a track, if
  they move) plus the view's camera angles; the browser projects. So orbiting a
  big mesh is nearly free in file size. The still frame for print is projected
  at build time with the same maths.
- **`legend([...], at)`** and **`panel(cx, cy, w, h, label)`** (from
  `lemur.anim.decorate`) — a legend and framed insets, usable in any plot.
