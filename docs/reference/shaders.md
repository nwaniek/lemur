# Shader reference

A compact summary of `!shader`. For an introduction, see
[Live shaders](../figures/shaders.md).

## The block

```lemur
!shader Title ^ref
	!src scene.glsl          %% required: the fragment shader
	!steps 3                 %% the shader's own steps: iStep runs 0 … 3
	!viewport full           %% body (default) | full (behind the text) | x y w h
	!quality 0.75            %% resolution factor (default 1)
	!sound drone             %% drone | aurora: off until the presenter presses m
```

`!width` and `!height` size a `body` viewport.

## The shader

```glsl
void mainImage(out vec4 fragColor, in vec2 fragCoord);
```

lemur compiles the source as GLSL ES 3.00 (WebGL 2) after adding
`precision highp float;`, the uniforms below, and a `main()` that calls
`mainImage`. Don't declare these yourself.

| Uniform | Type | |
|---|---|---|
| `iResolution` | `vec3` | canvas size in pixels (`z` = 1) |
| `iTime` | `float` | seconds the shader has run; it pauses while the slide is not shown |
| `iTimeDelta` | `float` | seconds since the previous frame |
| `iFrame` | `int` | frame counter |
| `iMouse` | `vec4` | pointer position over the canvas, in pixels |
| `iStep` | `float` | the step, eased: glides from one whole number to the next after a keypress |
| `iStepRaw` | `int` | the step being moved to |
| `iSteps` | `float` | the number of steps declared with `!steps` |

`#include "file.glsl"` on a line of its own is replaced by that file (relative
to the including file) when the deck is built.

## Behaviour

- **Steps.** The shader's steps come after the slide's other reveals (together
  with any animation's beats). Going back glides `iStep` back.
- **Resolution** starts at `!quality` × the canvas size and drops temporarily
  when frames take too long.
- **Contexts.** Only shaders on the current slide run; leaving a slide keeps
  its last frame as a still image, which the overview and printing show.
- **Errors.** A compile error is shown on the slide with its line numbers,
  counted in your file.
- **Sound.** `!sound` attaches a generative soundtrack synthesised in the
  browser, which follows the slide's steps. Sound is off until the presenter
  presses `m`. Once switched on, it plays on every slide with a soundtrack,
  until `m` is pressed again.
