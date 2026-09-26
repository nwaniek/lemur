// Conway's Game of Life on a 256 × 144 torus: every cell is a thread.
// Two buffers: each tick reads one and writes the other, then copies back.
const W = 256u;
const H = 144u;

@group(0) @binding(1) var<storage, read_write> cells: array<u32, W * H>;
@group(0) @binding(2) var<storage, read_write> next: array<u32, W * H>;

fn alive(x: i32, y: i32) -> u32 {
  let i = u32((y + i32(H)) % i32(H)) * W + u32((x + i32(W)) % i32(W));
  return cells[i];
}

//! threads W H
//! once
@compute @workgroup_size(16, 16)
fn seed(@builtin(global_invocation_id) id: vec3u) {
  let r = lmr_rand(id.y * W + id.x + lmr.seed * 7919u);
  cells[id.y * W + id.x] = select(0u, 1u, r < 0.3);
}

//! threads W H
@compute @workgroup_size(16, 16)
fn rule(@builtin(global_invocation_id) id: vec3u) {
  if (id.x >= W || id.y >= H) { return; }
  let x = i32(id.x);
  let y = i32(id.y);
  var n = 0u;
  for (var dy = -1; dy <= 1; dy++) {
    for (var dx = -1; dx <= 1; dx++) {
      if (dx != 0 || dy != 0) { n += alive(x + dx, y + dy); }
    }
  }
  let me = alive(x, y);
  next[id.y * W + id.x] = select(0u, 1u, n == 3u || (me == 1u && n == 2u));
}

//! threads W H
@compute @workgroup_size(16, 16)
fn copy(@builtin(global_invocation_id) id: vec3u) {
  if (id.x < W && id.y < H) { cells[id.y * W + id.x] = next[id.y * W + id.x]; }
}

fn mainImage(p: vec2f) -> vec4f {
  let g = vec2u(p / lmr.resolution * vec2f(f32(W), f32(H)));
  let on = f32(cells[min(g.y, H - 1u) * W + min(g.x, W - 1u)]);
  return vec4f(mix(vec3f(0.04, 0.05, 0.08), vec3f(0.43, 0.95, 0.71), on), 1.0);
}
