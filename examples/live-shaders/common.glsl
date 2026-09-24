// common.glsl — shared helpers for the live-shader deck (pulled in with
// `#include "common.glsl"`, which lemur resolves at build time).

#define PI 3.14159265

// hashes without sine (Dave Hoskins)
float hash12(vec2 p) {
    vec3 p3 = fract(vec3(p.xyx) * 0.1031);
    p3 += dot(p3, p3.yzx + 33.33);
    return fract((p3.x + p3.y) * p3.z);
}
float hash13(vec3 p3) {
    p3 = fract(p3 * 0.1031);
    p3 += dot(p3, p3.zyx + 31.32);
    return fract((p3.x + p3.y) * p3.z);
}

// value noise, and its analytic derivative (IQ)
float noise2(vec2 p) {
    vec2 i = floor(p), f = fract(p);
    vec2 u = f * f * (3.0 - 2.0 * f);
    return mix(mix(hash12(i), hash12(i + vec2(1, 0)), u.x),
               mix(hash12(i + vec2(0, 1)), hash12(i + vec2(1, 1)), u.x), u.y);
}
vec3 noised(vec2 p) {
    vec2 i = floor(p), f = fract(p);
    vec2 u = f * f * (3.0 - 2.0 * f);
    vec2 du = 6.0 * f * (1.0 - f);
    float a = hash12(i), b = hash12(i + vec2(1, 0)), c = hash12(i + vec2(0, 1)), d = hash12(i + vec2(1, 1));
    return vec3(a + (b - a) * u.x + (c - a) * u.y + (a - b - c + d) * u.x * u.y,
                du * (vec2(b - a, c - a) + (a - b - c + d) * u.yx));
}
float noise3(vec3 p) {
    vec3 i = floor(p), f = fract(p);
    vec3 u = f * f * (3.0 - 2.0 * f);
    return mix(mix(mix(hash13(i), hash13(i + vec3(1, 0, 0)), u.x),
                   mix(hash13(i + vec3(0, 1, 0)), hash13(i + vec3(1, 1, 0)), u.x), u.y),
               mix(mix(hash13(i + vec3(0, 0, 1)), hash13(i + vec3(1, 0, 1)), u.x),
                   mix(hash13(i + vec3(0, 1, 1)), hash13(i + vec3(1, 1, 1)), u.x), u.y), u.z);
}

const mat2 ROT2 = mat2(0.8, -0.6, 0.6, 0.8);

// fractional Brownian motion: octaves of noise, each twice as fine, half as strong
float fbm2(vec2 p, int oct) {
    float a = 0.5, s = 0.0;
    for (int i = 0; i < 12; i++) {
        if (i >= oct) break;
        s += a * noise2(p);
        p = ROT2 * p * 2.02;
        a *= 0.5;
    }
    return s;
}
float fbm3(vec3 p, int oct) {
    float a = 0.5, s = 0.0;
    for (int i = 0; i < 8; i++) {
        if (i >= oct) break;
        s += a * noise3(p);
        p = p * 2.03 + vec3(1.7, 9.2, 3.1);
        a *= 0.5;
    }
    return s;
}

// IQ's cosine palette
vec3 palette(float t, vec3 a, vec3 b, vec3 c, vec3 d) { return a + b * cos(6.28318 * (c * t + d)); }

// filmic tone mapping, gamma and a gentle vignette
vec3 aces(vec3 x) { return clamp((x * (2.51 * x + 0.03)) / (x * (2.43 * x + 0.59) + 0.14), 0.0, 1.0); }
vec3 finish(vec3 c, vec2 uv) {
    c = aces(c);
    c = pow(c, vec3(1.0 / 2.2));
    c *= 0.55 + 0.45 * pow(16.0 * uv.x * uv.y * (1.0 - uv.x) * (1.0 - uv.y), 0.15);
    return c;
}

// ease a (possibly fractional, eased) step into per-stage weights
float stage(float s, float k) { return clamp(1.0 - abs(s - k), 0.0, 1.0); }

// the aurora: vertical curtains of emission, sampled in horizontal slices;
// bright green at the lower edge, fading to red and violet higher up
vec3 auroraCol(float k) {
    return mix(vec3(0.12, 1.0, 0.45), vec3(0.8, 0.2, 0.75), smoothstep(0.15, 0.9, k));
}
vec3 aurora(vec3 ro, vec3 rd, float time, float strength, float speed) {
    vec3 acc = vec3(0.0);
    if (rd.y <= 0.01) return acc;
    float jit = hash13(rd * 1731.0);                // dither the slices: no banding
    for (int i = 0; i < 44; i++) {
        float k = (float(i) + jit) / 44.0;
        float h = 1800.0 + k * 2600.0;
        float t = (h - ro.y) / rd.y;
        vec2 p = (ro.xz + rd.xz * t) * 0.00032;
        vec2 q = p + 0.45 * vec2(fbm2(p * 1.3 + time * 0.02 * speed, 3),
                                 fbm2(p * 1.3 + 7.3 - time * 0.017 * speed, 3));
        float line = abs(sin(q.x * 2.4 + 1.9 * sin(q.y * 1.1 + time * 0.06 * speed) + 0.8 * q.y));
        float c = exp(-line * 16.0) + 0.3 * exp(-line * 4.0);
        c *= smoothstep(0.0, 0.08, k) * exp(-k * 2.6);
        acc += auroraCol(k) * c;
    }
    return acc * strength * smoothstep(0.0, 0.15, rd.y) / 44.0 * 7.0;
}

// stars: a sparse hashed grid of directions, twinkling
vec3 stars(vec3 rd, float time) {
    vec3 q = rd * 380.0;
    vec3 id = floor(q);
    float h = hash13(id);
    float s = step(0.9965, h) * smoothstep(0.55, 0.0, length(fract(q) - 0.5));
    vec3 tint = mix(vec3(0.8, 0.85, 1.0), vec3(1.0, 0.85, 0.7), hash13(id + 7.0));
    return s * tint * (0.55 + 0.45 * sin(time * (2.0 + 3.0 * h) + h * 60.0)) * 1.4;
}
