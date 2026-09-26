// The central limit theorem, a million samples a frame. Each thread draws one
// sample: the sum of k uniform numbers, standardised. It lands in one of 256
// bins, and many threads land in the same bin at the same time, so the count
// is an atomicAdd. The steps raise k: 1, 2, 3, 6, 24.
const BINS = 256u;
const SAMPLES = 1048576u;                            // 2^20: one per thread

@group(0) @binding(1) var<storage, read_write> hist: array<atomic<u32>, BINS>;

fn terms() -> u32 {
  var k = array<u32, 5>(1u, 2u, 3u, 6u, 24u);
  return k[min(lmr.step_raw, 4u)];
}

//! threads BINS
@compute @workgroup_size(64)
fn clear(@builtin(global_invocation_id) id: vec3u) {
  atomicStore(&hist[id.x], 0u);
}

//! threads SAMPLES
@compute @workgroup_size(256)
fn draw_sample(@builtin(global_invocation_id) id: vec3u) {
  let n = terms();
  var s = 0.0;
  for (var j = 0u; j < n; j++) {
    s += lmr_rand(lmr_hash(id.x ^ (lmr.tick * 2654435761u)) + j * 2246822519u + lmr.seed);
  }
  let z = (s - 0.5 * f32(n)) / sqrt(f32(n) / 12.0);  // mean 0, variance 1
  let bin = i32(floor((z + 4.0) / 8.0 * f32(BINS)));
  if (bin >= 0 && bin < i32(BINS)) {
    atomicAdd(&hist[u32(bin)], 1u);
  }
}

fn mainImage(p: vec2f) -> vec4f {
  let uv = p / lmr.resolution;
  var col = vec3f(0.035, 0.045, 0.075);
  let x0 = 0.05; let x1 = 0.95; let y0 = 0.08; let y1 = 0.94;
  let u = (uv.x - x0) / (x1 - x0);
  let v = (uv.y - y0) / (y1 - y0);
  let peak = f32(SAMPLES) * (8.0 / f32(BINS)) * 0.3989423;   // the normal's peak, in counts
  if (u >= 0.0 && u < 1.0 && v >= 0.0) {
    let h = f32(atomicLoad(&hist[u32(u * f32(BINS))])) / (peak * 1.12);
    if (v < h) {
      col = mix(vec3f(0.16, 0.42, 0.6), vec3f(0.43, 0.95, 0.71), v / max(h, 1e-3));
    }
    let z = u * 8.0 - 4.0;
    let g = exp(-0.5 * z * z) / 1.12;                // the normal density, same scale
    let px = 1.0 / (lmr.resolution.y * (y1 - y0));
    col = mix(col, vec3f(1.0, 0.82, 0.4), 1.0 - smoothstep(1.2 * px, 2.8 * px, abs(v - g)));
  }
  if (abs(uv.y - y0) * lmr.resolution.y < 1.0 && uv.x > x0 && uv.x < x1) {
    col = vec3f(0.55, 0.6, 0.66);
  }
  return vec4f(col, 1.0);
}
