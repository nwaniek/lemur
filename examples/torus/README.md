# Curvature on a torus (GPU views)

`python3 lmr2svg.py examples/torus/deck.lmr -o torus.html`

A short lecture drawn with **GPU views**. `View(renderer="gpu")` has the
deck's player draw the figure with WebGL and a depth buffer, so a torus, which
is not convex, hides itself correctly from every side. Curves on it get their
hidden stretches dashed, and the outline is its smooth silhouette for the
current camera.

| animation | shows |
|---|---|
| `shape.py` | the torus from above, the side and underneath (`Figure(view, Torus(R, r))`, `fig.backdrop()`) |
| `frame.py` | a meridian and a parallel through *p*, the tangent plane, `T_u` and `T_v` |
| `curvature.py` | the solid tinted by Gaussian curvature (`fig.solid(tint=…)`), the two flat circles |
| `geodesics.py` | geodesics from one point, integrated from the geodesic equations |

Printing, or saving as PDF, gives an exact **vector** still of each figure
(faces sorted for the final camera, visible lines, dashed hidden lines), never
a screenshot of the canvas. `torus_lib.py` holds the shared geometry.
