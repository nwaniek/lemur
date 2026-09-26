// Gray–Scott reaction–diffusion on a 256 × 256 torus. Two chemicals u and v
// diffuse at different rates and react (u + 2v → 3v); feed and kill rates pick
// the pattern. The grid lives in two buffers, a and b: one tick reads a and
// writes b, then reads b and writes a. The steps move (feed, kill) through
// four regimes, blended by the eased step.
const W = 256u;
const H = 256u;

@group(0) @binding(1) var<storage, read_write> a: array<vec2f, W * H>;
@group(0) @binding(2) var<storage, read_write> b: array<vec2f, W * H>;

fn at(x: i32, y: i32) -> u32 {
  return u32((y + i32(H)) % i32(H)) * W + u32((x + i32(W)) % i32(W));
}

fn feed_kill() -> vec2f {
  var fk = array<vec2f, 4>(vec2f(0.0367, 0.0649),    // dividing spots
                           vec2f(0.0290, 0.0570),    // coral
                           vec2f(0.0390, 0.0580),    // worms and mazes
                           vec2f(0.0620, 0.0609));   // holes
  let s = clamp(lmr.step, 0.0, 3.0);
  let i = u32(floor(s));
  return mix(fk[i], fk[min(i + 1u, 3u)], s - floor(s));
}

fn react(c: vec2f, lap: vec2f) -> vec2f {
  let fk = feed_kill();
  let uvv = c.x * c.y * c.y;
  let du = 1.0 * lap.x - uvv + fk.x * (1.0 - c.x);
  let dv = 0.5 * lap.y + uvv - (fk.x + fk.y) * c.y;
  return clamp(c + vec2f(du, dv), vec2f(0.0), vec2f(1.0));
}

fn lap_a(x: i32, y: i32) -> vec2f {
  return 0.2 * (a[at(x - 1, y)] + a[at(x + 1, y)] + a[at(x, y - 1)] + a[at(x, y + 1)])
       + 0.05 * (a[at(x - 1, y - 1)] + a[at(x + 1, y - 1)] + a[at(x - 1, y + 1)] + a[at(x + 1, y + 1)])
       - a[at(x, y)];
}

fn lap_b(x: i32, y: i32) -> vec2f {
  return 0.2 * (b[at(x - 1, y)] + b[at(x + 1, y)] + b[at(x, y - 1)] + b[at(x, y + 1)])
       + 0.05 * (b[at(x - 1, y - 1)] + b[at(x + 1, y - 1)] + b[at(x - 1, y + 1)] + b[at(x + 1, y + 1)])
       - b[at(x, y)];
}

//! threads W H
//! once
@compute @workgroup_size(16, 16)
fn seed(@builtin(global_invocation_id) id: vec3u) {
  let blob = id.xy / 12u;                            // random 12 × 12 squares of v
  let on = lmr_rand(blob.x * 131u + blob.y * 7919u + lmr.seed * 104729u) < 0.1;
  a[id.y * W + id.x] = vec2f(1.0, select(0.0, 1.0, on));
}

//! threads W H
@compute @workgroup_size(16, 16)
fn step_ab(@builtin(global_invocation_id) id: vec3u) {
  let x = i32(id.x);
  let y = i32(id.y);
  b[at(x, y)] = react(a[at(x, y)], lap_a(x, y));
}

//! threads W H
@compute @workgroup_size(16, 16)
fn step_ba(@builtin(global_invocation_id) id: vec3u) {
  let x = i32(id.x);
  let y = i32(id.y);
  a[at(x, y)] = react(b[at(x, y)], lap_b(x, y));
}

fn v_at(g: vec2f) -> f32 {                           // bilinear, wrapping
  let i = vec2i(floor(g - 0.5));
  let f = fract(g - 0.5);
  let v00 = a[at(i.x, i.y)].y;
  let v10 = a[at(i.x + 1, i.y)].y;
  let v01 = a[at(i.x, i.y + 1)].y;
  let v11 = a[at(i.x + 1, i.y + 1)].y;
  return mix(mix(v00, v10, f.x), mix(v01, v11, f.x), f.y);
}

fn mainImage(p: vec2f) -> vec4f {
  let v = v_at(p / lmr.resolution.y * f32(H));
  var col = mix(vec3f(0.02, 0.03, 0.06), vec3f(0.2, 0.47, 0.72), smoothstep(0.08, 0.25, v));
  col = mix(col, vec3f(0.96, 0.88, 0.7), smoothstep(0.25, 0.45, v));
  return vec4f(col, 1.0);
}
