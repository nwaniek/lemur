// flow.glsl — a fluid without a solver: the velocity is the curl of a noise
// stream function (divergence-free by construction), shown with animated line
// integral convolution — noise smeared along the streamlines, with pulses
// travelling down them. Steps: more octaves (turbulence), a vortex pair, ink.
#include "common.glsl"

float psi(vec2 p, float t, float s) {
    int oct = 2 + int(min(s, 3.0) + 0.5);
    float f = fbm2(p * 0.9 + vec2(0.13 * t, -0.07 * t), oct) * 1.6;
    // a vortex pair that swims across (step 2 on)
    float vp = smoothstep(1.5, 2.2, s);
    vec2 c = vec2(0.6 * sin(t * 0.21), 0.35 * cos(t * 0.17));
    f += vp * (exp(-dot(p - c - vec2(0.25, 0), p - c - vec2(0.25, 0)) * 6.0)
             - exp(-dot(p - c + vec2(0.25, 0), p - c + vec2(0.25, 0)) * 6.0)) * 0.9;
    return f;
}

vec2 vel(vec2 p, float t, float s) {
    float e = 0.004;
    float a = psi(p + vec2(0, e), t, s), b = psi(p - vec2(0, e), t, s);
    float c = psi(p + vec2(e, 0), t, s), d = psi(p - vec2(e, 0), t, s);
    return vec2(a - b, -(c - d)) / (2.0 * e);                 // v = curl ψ = (ψ_y, −ψ_x)
}

float grain(vec2 p) { return hash12(floor(p * 220.0)); }

void mainImage(out vec4 fragColor, in vec2 fragCoord) {
    vec2 uv = fragCoord / iResolution.xy;
    vec2 p = (2.0 * fragCoord - iResolution.xy) / iResolution.y;
    float t = iTime, s = iStep;
    float acc = 0.0, wsum = 0.0;
    const int N = 14;
    float h = 0.0045;
    for (int dir = -1; dir <= 1; dir += 2) {                    // trace both ways
        vec2 x = p;
        for (int i = 0; i < N; i++) {
            vec2 v = vel(x, t, s);
            x += float(dir) * h * v / (length(v) + 1e-3);
            float sArc = float(dir) * float(i + 1);
            float w = 0.5 + 0.5 * sin(sArc * 0.45 - t * 6.0 + 6.28 * grain(x * 0.35));   // travelling pulses
            acc += grain(x) * w;
            wsum += w;
        }
    }
    float lic = acc / max(wsum, 1e-3);
    vec2 v = vel(p, t, s);
    float speed = length(v);
    float ink = smoothstep(2.5, 3.2, s);
    vec3 cool = palette(0.55 + 0.15 * speed, vec3(0.3, 0.45, 0.6), vec3(0.3, 0.35, 0.4), vec3(1.0), vec3(0.0, 0.1, 0.2));
    vec3 warm = palette(0.2 + 0.2 * speed, vec3(0.55, 0.3, 0.2), vec3(0.45, 0.3, 0.25), vec3(1.0, 0.8, 0.6), vec3(0.0, 0.15, 0.3));
    vec3 base = mix(cool, warm, ink);
    vec3 col = base * (0.25 + 1.25 * lic * lic) * (0.4 + 0.6 * smoothstep(0.0, 1.5, speed));
    fragColor = vec4(finish(col * 1.1, uv), 1.0);
}
