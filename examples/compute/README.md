# Thinking in Parallel (WebGPU compute)

`python3 lmr2svg.py examples/compute/deck.lmr -o compute.html`

Four `!compute` programs: WGSL compute kernels that run live on the GPU,
stepped by the slides. Open the deck in a browser with WebGPU (current Chrome,
Edge or Safari; Firefox on Windows).

| program | shows | steps |
|---|---|---|
| `reduce.wgsl` | a tree reduction: 32 threads, workgroup memory, barriers; the picture follows the highlighted code (`!steps slide`) | load, five levels, the sum |
| `clt.wgsl` | a million threads, one sample each, counted into 256 bins with `atomicAdd` | samples become sums of 1, 2, 3, 6, 24 uniforms |
| `grayscott.wgsl` | Gray–Scott reaction–diffusion on a torus, ping-ponging between two buffers | spots → coral → mazes → holes |
| `flow.wgsl` | 2^18 particles in a curl-noise flow, splatted into a density grid with atomics | a vortex, then a counter-rotating pair |

Each program declares its buffers with fixed sizes, puts `//! threads N` above
every kernel (`//! once` for the one that initialises), and draws with
`mainImage`. lemur provides `lmr` (step, time, dt, tick, seed, resolution,
mouse) and `lmr_rand`. Going back through the slides restores each simulation
as it was; jumping ahead replays it.
