# Live shaders

`!shader` runs a GLSL fragment shader **live on the GPU**, right on the slide.
Every pixel is computed sixty times a second, and the slide's steps drive the
scene. Use it for visualisations that are too rich to precompute (noise,
fractals, ray-marched landscapes, fluids), and for the occasional moment of
wonder.

```{lemur-example}
:files: shader/rings.glsl
:source:

!slide Interference

!shader
	!src rings.glsl
	!steps 3
```

Shaders need WebGL 2, which every current desktop browser has.

## Writing a shader

A shader follows the convention of [Shadertoy](https://www.shadertoy.com/): a
function that computes one pixel's colour.

```glsl
void mainImage(out vec4 fragColor, in vec2 fragCoord) {
    vec2 uv = fragCoord / iResolution.xy;          // 0..1 across the canvas
    fragColor = vec4(uv, 0.5 + 0.5 * sin(iTime), 1.0);
}
```

It can use these uniforms:

| Uniform | Type | Meaning |
|---|---|---|
| `iResolution` | `vec3` | the canvas size in pixels |
| `iTime`, `iTimeDelta` | `float` | seconds the shader has run (it pauses while its slide is not shown), and since the last frame |
| `iFrame` | `int` | the frame number |
| `iMouse` | `vec4` | the pointer over the canvas |
| `iStep` | `float` | the shader's step, **eased**: a keypress glides it from one whole number to the next |
| `iStepRaw` | `int` | the step it is heading for |
| `iSteps` | `float` | the number of steps (`!steps`) |

Since the names match Shadertoy's, most shaders from there can be pasted in.
Use `iStep` to change the scene with the talk: fade a new term in, move the
camera, turn day into night. Because it is eased, the change is a smooth glide
rather than a jump.

`#include "file.glsl"` inserts another file, relative to the shader, when the
deck is built. Shared noise functions and palettes can therefore live in one
file.

## Directives

| Directive | Meaning |
|---|---|
| `!src file.glsl` | the fragment shader (required) |
| `!steps N` | the shader takes *N* steps; `iStep` runs from 0 to *N*. They follow the slide's other reveals, alongside any animation's beats |
| `!viewport body\|full\|x y w h` | where it is drawn, as for [`!anim`](animations.md). `full` fills the whole slide **behind** its text, a live background |
| `!width`, `!height` | the size, for a `body` viewport |
| `!quality q` | the resolution as a factor of the canvas size (default 1; e.g. `0.5` for heavy shaders) |
| `!sound drone\|aurora` | a generative soundtrack for the slide, silent until the presenter presses `m` |

The resolution also adapts by itself: if the frame rate drops, the shader
renders at a lower resolution until it recovers.

## When things go wrong

A shader that does not compile shows its error log on the slide, with line
numbers from your file, and the rest of the deck is unaffected. In the overview
and when printing, a shader slide shows its last rendered frame.

## Performance

A browser keeps only a limited number of GPU contexts, so a shader only runs
while its slide is on screen. Each pixel costs the full shader, so keep
ray-marching loops bounded, and use `!quality` for full-screen scenes on
high-resolution displays.

The `live-shaders` example is a whole deck of scenes: an aurora, a ray-marched
terrain flyover from dawn to night, volumetric clouds, a curl-noise fluid, and
fractal noise gaining octaves one step at a time. See the
[shader reference](../reference/shaders.md) for a compact summary.
