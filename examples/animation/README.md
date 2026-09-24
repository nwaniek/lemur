# Animation

`python3 lmr2svg.py examples/animation/deck.lmr -o animation.html`

- `!anim` with `!src <module.py>` embeds a **build-time animation** — the module
  is a `lemur.anim` (wanim-style) `Anim` subclass, run at build time and baked to
  SVG outlines, so the output stays one self-contained file with no runtime deps.
- Each `self.next()` beat is a **slide step**: press → to draw the axes, the sine
  on −2π..2π, then highlight −π..π. The animation tweens in real time.
- `!viewport body` (default) renders it in the body region; `!viewport full`
  uses the whole slide, or `!viewport "x y w h"` a specific rect. The world/camera
  live in the `.py`; the slide author only places the viewport.
