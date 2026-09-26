// A quarter of a million particles in a curl-noise flow. Every tick, each
// thread moves one particle and adds it to a density grid (an atomicAdd: many
// particles share a cell); another kernel lets the grid fade, so it keeps a
// short trail. Step 1 adds a vortex, step 2 a counter-rotating pair.
const N = 262144u;                                   // 2^18 particles
const GW = 480u;
const GH = 270u;
const A = 1.7777778;                                 // the domain: [0, A] × [0, 1]
const LIFE = 8.0;

struct Particle { pos: vec2f, age: f32, pad: f32 }

@group(0) @binding(1) var<storage, read_write> ps: array<Particle, N>;
@group(0) @binding(2) var<storage, read_write> density: array<atomic<u32>, GW * GH>;

fn hash2(p: vec2i) -> f32 {
  return lmr_rand((u32(p.x) * 73856093u) ^ (u32(p.y) * 19349663u));
}

fn vnoise(p: vec2f) -> f32 {
  let i = vec2i(floor(p));
  let f = fract(p);
  let u = f * f * (3.0 - 2.0 * f);
  return mix(mix(hash2(i), hash2(i + vec2i(1, 0)), u.x),
             mix(hash2(i + vec2i(0, 1)), hash2(i + vec2i(1, 1)), u.x), u.y);
}

fn potential(p: vec2f) -> f32 {
  let t = lmr.time;
  return vnoise(p * 2.2 + vec2f(0.0, t * 0.05)) + 0.5 * vnoise(p * 4.7 - vec2f(t * 0.07, 0.0));
}

fn swirl(q: vec2f, spin: f32) -> vec2f {             // a vortex, pulling gently inward
  let w = exp(-dot(q, q) * 9.0);
  return (vec2f(-q.y, q.x) * spin * 2.2 - q * 0.35) * w;
}

fn field(p: vec2f) -> vec2f {
  let e = 0.004;
  let dx = (potential(p + vec2f(e, 0.0)) - potential(p - vec2f(e, 0.0))) / (2.0 * e);
  let dy = (potential(p + vec2f(0.0, e)) - potential(p - vec2f(0.0, e))) / (2.0 * e);
  var v = vec2f(dy, -dx) * 0.05;                     // curl: divergence-free
  let s1 = clamp(lmr.step, 0.0, 1.0);
  let s2 = clamp(lmr.step - 1.0, 0.0, 1.0);
  v += swirl(p - vec2f(A * 0.5, 0.5), 1.0) * s1 * (1.0 - s2);
  v += (swirl(p - vec2f(A * 0.32, 0.5), 1.0) + swirl(p - vec2f(A * 0.68, 0.5), -1.0)) * s2;
  return v;
}

fn respawn(i: u32) -> vec2f {
  let k = i * 2u + lmr.tick * 7919u + lmr.seed * 104729u;
  return vec2f(lmr_rand(k) * A, lmr_rand(k + 1u));
}

//! threads N
//! once
@compute @workgroup_size(256)
fn init(@builtin(global_invocation_id) id: vec3u) {
  ps[id.x].pos = respawn(id.x);
  ps[id.x].age = lmr_rand(id.x + 99u) * LIFE;
}

//! threads GW GH
@compute @workgroup_size(16, 16)
fn fade(@builtin(global_invocation_id) id: vec3u) {
  if (id.x < GW && id.y < GH) {
    let i = id.y * GW + id.x;
    atomicStore(&density[i], atomicLoad(&density[i]) * 7u / 8u);
  }
}

//! threads N
@compute @workgroup_size(256)
fn advect(@builtin(global_invocation_id) id: vec3u) {
  var q = ps[id.x];
  q.pos += field(q.pos) * lmr.dt;
  q.age += lmr.dt;
  if (q.age > LIFE) {
    q.pos = respawn(id.x);
    q.age = 0.0;
  }
  q.pos = vec2f(fract(q.pos.x / A) * A, fract(q.pos.y));
  ps[id.x] = q;
  let g = vec2u(q.pos / vec2f(A, 1.0) * vec2f(f32(GW), f32(GH)));
  if (g.x < GW && g.y < GH) {
    atomicAdd(&density[g.y * GW + g.x], 1u);
  }
}

fn mainImage(p: vec2f) -> vec4f {
  let g = vec2u(p / lmr.resolution * vec2f(f32(GW), f32(GH)));
  let d = f32(atomicLoad(&density[min(g.y, GH - 1u) * GW + min(g.x, GW - 1u)]));
  let k = 1.0 - exp(-d * 0.035);
  var col = mix(vec3f(0.02, 0.025, 0.05), vec3f(0.1, 0.45, 0.62), smoothstep(0.0, 0.5, k));
  col = mix(col, vec3f(1.0, 0.86, 0.55), smoothstep(0.5, 1.0, k));
  return vec4f(col, 1.0);
}
