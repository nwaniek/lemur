# Moving sand on a sphere (optimal transport, with particles)

`python3 lmr2svg.py examples/optimal-transport/deck.lmr -o optimal-transport.html`

A short lecture on optimal transport on a curved surface, told with a particle
system of 180 grains on a sphere, in the illustrated style of
`lemur.anim.illustrate` (lit sphere, silhouette, contact shadow, haloed dots,
hidden things hidden).

- **`measures.py`** — the source μ (a blob) blooms grain by grain; the target ν
  (a ring) appears as empty slots; the camera swings round the globe.
- **`transport.py`** — the optimal map: every grain glides along a great circle
  to its slot while a trail is drawn exactly under it; then the cost `W₂²`.
- **`compare.py`** — a random matching (a tangle, higher cost) against the
  optimal one (no two paths cross).
- **`sinkhorn.py`** — entropic OT for ε = 4 … 0.05: each grain goes to the
  barycentre of its blurry plan; the ring collapses for large ε and sharpens as
  ε → 0.
- **`finale.py`** — full-screen: the same sand reshaped blob → ring → two
  blobs → spiral → heart → blob, each leg the optimal plan, the camera drifting.

`otlib.py` holds the maths (sampling measures on the sphere, squared geodesic
cost, exact assignment via `scipy.optimize.linear_sum_assignment`, log-domain
Sinkhorn, barycentric projection) and `Flow`, the particle state: N grains
moving along great circles from A to B as one tracker goes 0 → 1. Every grain
keeps the colour of its direction around the source centre, so you can follow
where it goes. Needs `scipy`.
