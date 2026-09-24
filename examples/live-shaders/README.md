# A World Made of Maths (live GPU shaders)

`python3 lmr2svg.py examples/live-shaders/deck.lmr -o live-shaders.html` — about 0.5 MB.

A demoscene homage (after *Elevated* by Rgba & TBC) that shows the `!shader`
block: GLSL fragment shaders that run **live on the GPU**, right in the slide,
driven by the slide steps. Open it in a browser with WebGL 2, press → to move
the scenes on, and **m** for a generative soundtrack.

| scene | what it shows | steps |
|---|---|---|
| `aurora.glsl` | polar lights over a frozen lake, the title slide | faint arc → curtains → violet corona → substorm |
| `fbm.glsl` | fractional Brownian motion as a relief map | one octave per step |
| `spheretrace.py` | *build-time* lemur animation: sphere tracing with an SDF | the ray, then its steps |
| `terrain.glsl` | a raymarched, eroded landscape flyover with lake, fog, soft shadows | dawn → day → dusk → aurora night |
| `clouds.glsl` | volumetric clouds (Beer–Lambert, Henyey–Greenstein, powder) | fair → cumulus → sunset → storm |
| `flow.glsl` | a curl-noise "fluid", shown with animated line integral convolution | turbulence → vortex pair → ink |
| `finale.glsl` | the flyover again, straight into the night (`#define` + `#include`) | — |

`common.glsl` holds the shared pieces (hashes, value noise with derivatives,
fbm, the aurora, stars, tone mapping); lemur resolves `#include "…"` at build
time. `style.py` is the night-sky design of the deck.

**Writing your own:** a shader is Shadertoy's `mainImage(out vec4, in vec2)`
with `iResolution`, `iTime`, `iTimeDelta`, `iFrame`, `iMouse`, plus lemur's
`iStep` (the slide step, eased — 0 … `!steps`), `iStepRaw` and `iSteps`.
`!viewport full` draws behind the slide's text; `!quality 0.5` caps the
resolution (it also adapts on its own to hold the frame rate); `!sound drone`
or `!sound aurora` attaches a soundtrack (off until **m**). A compile error is
shown on the slide with the line numbers of your file. The overview grid and
print show the last rendered frame.
