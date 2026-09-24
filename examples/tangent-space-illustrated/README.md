# The tangent space — illustrated

`python3 lmr2svg.py examples/tangent-space-illustrated/deck.lmr -o tangent-space-illustrated.html`

The same lecture as [`tangent-space/`](../tangent-space/), redrawn in the style of
the figures in a geometry paper (think Keenan Crane's discrete differential
geometry notes), with a touch of our own:

- **Opaque, lit surfaces.** `View.shaded_surface()` (lemur.anim) builds a surface
  from small filled quads, each shaded once by a cool key light and a *warm fill
  light* (our touch), with a faint darker mesh on top. Faces turned away from the
  camera are hidden every frame, so the convex dome occludes itself correctly
  while the camera orbits. A coarse copy underneath fills the thin slivers that
  hiding whole faces leaves along the outline.
- **A crisp silhouette and a soft contact shadow**, recomputed for every camera
  angle, instead of a wireframe and a ground plane.
- **Haloed marks.** Curves, vectors and dots sit on a paper-white halo, so they
  read cleanly against the mesh. Anything behind the dome is drawn as a
  **hidden line**, the technical-illustration convention: thin, dashed and faint,
  so a path stays readable all the way round while the dome stays opaque.
  Vectors and tangent sheets whose base point is behind the dome fade to a ghost.
- **Paper and ink.** A warm paper page, ink text in Source Serif (next to
  LaTeX's Latin Modern), one orange accent (`style.py`, picked up automatically).
  The tangent plane is a translucent sheet of warm paper with a fine grid.

`ill.py` holds the geometry and this whole drawing vocabulary; the five scene
modules (`world.py`, `plane.py`, `logmap.py`, `wrap.py`, `bundle.py`) tell the
same story as the dark version.
