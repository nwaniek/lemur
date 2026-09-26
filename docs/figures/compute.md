# Compute shaders

`!compute` runs a **WebGPU** program live on the slide: compute kernels that
work on buffers of data, thousands or millions of threads at a time, and a
function that draws the result. Use it to show a parallel algorithm while it
runs (a reduction, a histogram with atomics, a prefix sum) or to put a
simulation on a slide (particles, reaction–diffusion, cellular automata,
fluids). The slide's steps drive it, and going back and forth through a talk
works as it should.

```{lemur-example}
:files: compute/life.wgsl
:source:

!slide The Game of Life, one thread per cell

!compute
	!src life.wgsl
	!rate 12
```

`!compute` needs a browser with WebGPU: current Chrome, Edge and Safari, and
Firefox on Windows. On Linux, Chrome may need WebGPU switched on in
`chrome://flags`. Where WebGPU is missing, the slide says so instead of going
blank. For fragment shaders that run everywhere, see
[`!shader`](shaders.md).

## The program

The WGSL file holds three kinds of things.

**Storage buffers** hold the data. Declare them in group 0 from binding 1 on,
with a fixed size. lemur reads the sizes when the deck is built and creates the
buffers, zero-filled:

```wgsl
const W = 256u;
const H = 144u;
@group(0) @binding(1) var<storage, read_write> cells: array<u32, W * H>;
@group(0) @binding(2) var<storage, read_write> next: array<u32, W * H>;
```

Element types may be scalars, vectors, matrices, atomics and structs; lemur
applies WGSL's memory layout rules. Integer `const`s can be used in sizes.

**Kernels** are `@compute` functions. A `//! threads` line above each one says
how many threads to run: one, two or three counts, as in `//! threads 65536`
or `//! threads W H`. lemur rounds the threads up to whole workgroups, so
guard the edges when the counts don't divide evenly. The kernels run in the
order they appear in the file, once per **tick**. A kernel marked `//! once`
runs only when the simulation starts, to set up its data:

```wgsl
//! threads W H
//! once
@compute @workgroup_size(16, 16)
fn seed(@builtin(global_invocation_id) id: vec3u) {
  cells[id.y * W + id.x] = select(0u, 1u, lmr_rand(id.y * W + id.x) < 0.3);
}

//! threads W H
@compute @workgroup_size(16, 16)
fn rule(@builtin(global_invocation_id) id: vec3u) { /* … */ }
```

**`mainImage`** draws the picture, as in a Shadertoy shader. It is called for
every pixel, with pixel coordinates whose origin is at the bottom left, and can
read any buffer:

```wgsl
fn mainImage(fragCoord: vec2f) -> vec4f {
  let g = vec2u(fragCoord / lmr.resolution * vec2f(f32(W), f32(H)));
  return vec4f(vec3f(f32(cells[g.y * W + g.x])), 1.0);
}
```

## What lemur provides

Every program can use a uniform `lmr` and two helpers:

| | |
|---|---|
| `lmr.step` | the step, eased: a keypress glides it from one whole number to the next |
| `lmr.step_raw` | the step as a whole number (`u32`) |
| `lmr.steps` | the number of steps |
| `lmr.time`, `lmr.dt` | simulation time and the fixed timestep, in seconds (`1 / !rate`) |
| `lmr.tick`, `lmr.frame` | the tick and frame counters |
| `lmr.seed` | the seed (`!seed`) |
| `lmr.resolution`, `lmr.mouse` | the canvas size in pixels, and the pointer (`xy`) over it |
| `lmr_hash(x: u32) -> u32` | a fast integer hash (PCG) |
| `lmr_rand(x: u32) -> f32` | a hash to `[0, 1)`: a random number for every thread and tick |

Binding 0 belongs to `lmr`, and your buffers start at binding 1.

## Directives

| Directive | Meaning |
|---|---|
| `!src file.wgsl` | the program (required); `#include "file.wgsl"` lines are resolved when the deck is built |
| `!steps N` | the program takes *N* steps of its own, which follow the slide's other reveals |
| `!steps slide` | the program follows the slide's **own** steps instead, running alongside its bullets, code highlights and pauses |
| `!rate R` | simulation ticks per second (default 60) |
| `!seed S` | the seed in `lmr.seed` (default 1) |
| `!warmup T` | seconds of simulation replayed per step when jumping ahead (default 2) |
| `!viewport body\|full\|x y w h`, `!width`, `!height` | where it is drawn, as for [`!anim`](animations.md); `full` puts it behind the slide's text |
| `!quality q` | the resolution as a factor of the canvas size (default 1) |

## Steps, going back, and jumping

A simulation has a history, but a talk goes back and jumps around. lemur keeps
the two consistent:

- The simulation advances in fixed ticks (`!rate`) from a fixed seed, so it
  runs the same way every time.
- Whenever a step is entered, the buffers are copied. Going back to a step
  restores the copy, so you see the state as it was when you first got there.
- Jumping ahead to a step not yet seen (a reload, the overview) replays the
  missing steps, `!warmup` seconds of simulation each.
- Only the slide on screen runs. A slide keeps its state while you are
  elsewhere.

## Following the slide: code and picture in step

With `!steps slide`, the program sees the slide's own step. It can then
illustrate a code block whose highlighted lines step through the same
algorithm:

```{lemur-example}
:files: compute/reduce.wgsl
:step: 3

!slide A parallel sum

!columns[42 58]
	!column
		:: wgsl[1-2|4-6|4-6|4-6|4-6|4-6|9]
			s[i] = vals[i];
			workgroupBarrier();
			for (var d = 1u; d < N; d *= 2u) {
			  if (i % (2u * d) == 0u) {
			    s[i] += s[i + d];
			  }
			  workgroupBarrier();
			}
			if (i == 0u) { total = s[0]; }
	!column
		!compute
			!src reduce.wgsl
			!steps slide
```

## Atomics

Many threads writing to the same place need atomics. Here a million threads
each draw one sample and add it to one of 256 histogram bins with `atomicAdd`.
Each step makes every sample a sum of more uniform numbers, and the histogram
turns into the normal curve:

```{lemur-example}
:files: compute/clt.wgsl
:source:
:step: 3

!slide The central limit theorem, live

!compute
	!src clt.wgsl
	!steps 4
```

## When something is wrong

lemur checks the declarations when the deck is built. It reports mistakes with
the file and line, and shows the message on the slide: a buffer without a fixed
size, a kernel without `//! threads`, a missing `mainImage`, a binding used
twice. Errors that only the GPU's compiler finds are shown on the slide when it
runs, again with lines from your file. If the GPU is reset while the deck runs,
the program starts over on the new device and replays to the current step.

## Printing and the overview

The overview shows a slide's last frame once the slide has run. Printing shows
the frame too, for slides you have visited. A program never run in this
browser session prints as an empty frame.

The `compute` example deck has four programs to start from: a tree reduction
with barriers and workgroup memory, a million-sample histogram with atomics,
Gray–Scott reaction–diffusion, and a quarter of a million particles in a flow
field.
