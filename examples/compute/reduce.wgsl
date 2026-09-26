// A tree reduction: the 32 threads of one workgroup sum 32 numbers in
// log2(32) = 5 levels, meeting at a barrier after each. `levels` keeps every
// level, so mainImage can draw the tree; the slide's step says how much of it
// to show (this block follows the slide's own steps).
const N = 32u;
const LEVELS = 6u;                                   // the input + 5 levels

@group(0) @binding(1) var<storage, read_write> vals: array<f32, N>;
@group(0) @binding(2) var<storage, read_write> levels: array<f32, N * LEVELS>;

var<workgroup> s: array<f32, N>;

//! threads N
//! once
@compute @workgroup_size(32)
fn init(@builtin(global_invocation_id) id: vec3u) {
  vals[id.x] = floor(1.0 + 9.0 * lmr_rand(id.x + 977u * lmr.seed));
}

//! threads N
@compute @workgroup_size(32)
fn reduce(@builtin(local_invocation_index) i: u32) {
  s[i] = vals[i];
  workgroupBarrier();
  levels[i] = s[i];
  var level = 1u;
  for (var d = 1u; d < N; d = d * 2u) {
    if (i % (2u * d) == 0u) {
      s[i] += s[i + d];
    }
    workgroupBarrier();
    levels[level * N + i] = s[i];
    level += 1u;
  }
}

// -- drawing ------------------------------------------------------------------

fn sd_box(p: vec2f, b: vec2f, r: f32) -> f32 {
  let q = abs(p) - b + r;
  return length(max(q, vec2f(0.0))) + min(max(q.x, q.y), 0.0) - r;
}

fn sd_seg(p: vec2f, a: vec2f, b: vec2f) -> f32 {
  let pa = p - a;
  let ba = b - a;
  let h = clamp(dot(pa, ba) / dot(ba, ba), 0.0, 1.0);
  return length(pa - ba * h);
}

fn cell(i: u32, r: u32) -> vec2f {
  let W = lmr.resolution.x;
  let H = lmr.resolution.y;
  return vec2f(W * 0.04 + (f32(i) + 0.5) * W * 0.92 / f32(N), H * 0.88 - f32(r) * H * 0.155);
}

fn mainImage(p: vec2f) -> vec4f {
  var col = vec3f(0.035, 0.045, 0.075);
  let cw = lmr.resolution.x * 0.92 / f32(N);
  let half = vec2f(cw * 0.4, min(cw * 0.9, lmr.resolution.y * 0.06));
  let shown = lmr.step - 1.0;                        // step 1: the input; 2..6: a level each
  let done = clamp(lmr.step - 6.0, 0.0, 1.0);        // step 7: the sum
  let total = levels[(LEVELS - 1u) * N];
  for (var r = 0u; r < LEVELS; r++) {
    let vis = clamp(shown - f32(r) + 1.0, 0.0, 1.0);
    if (vis <= 0.0) { break; }
    let d = 1u << r;
    let current = clamp(1.0 - abs(shown - f32(r)), 0.0, 1.0) * (1.0 - done);
    for (var i = 0u; i < N; i += d) {
      let c = cell(i, r);
      if (r > 0u) {                                  // the two partial sums it adds
        let a = cell(i, r - 1u) - vec2f(0.0, half.y);
        let b = cell(i + d / 2u, r - 1u) - vec2f(0.0, half.y);
        let top = c + vec2f(0.0, half.y);
        let dl = min(sd_seg(p, a, top), sd_seg(p, b, top));
        col = mix(col, vec3f(0.33, 0.42, 0.55), vis * (1.0 - smoothstep(0.6, 1.8, dl)));
      }
      let v = levels[r * N + i] / max(total, 1.0) * f32(N / d);   // share of a fair split
      let q = p - c;
      let box = sd_box(q, half, 3.0);
      var tint = mix(vec3f(0.36, 0.77, 0.87), vec3f(1.0, 0.7, 0.28), current);
      if (r == LEVELS - 1u) { tint = mix(tint, vec3f(1.0, 0.85, 0.35), done); }
      let fill = select(0.18, 1.0, q.y < -half.y + 2.0 * half.y * clamp(v * 0.5, 0.08, 1.0));
      col = mix(col, tint * fill, vis * (1.0 - smoothstep(-1.0, 0.5, box)));
      col = mix(col, tint, vis * (1.0 - smoothstep(0.0, 1.5, abs(box))));
    }
  }
  return vec4f(col, 1.0);
}
