// fbm.glsl — fractional Brownian motion, one octave per step: a relief map
// (hillshade + contour lines + hypsometric tints) that gains detail as octaves
// are added. The newest octave fades in as iStep glides.
#include "common.glsl"

float heightAt(vec2 p, float octs) {
    float a = 0.5, s = 0.0;
    for (int i = 0; i < 8; i++) {
        float w = clamp(octs - float(i), 0.0, 1.0);          // fractional last octave
        if (w <= 0.0) break;
        s += a * noise2(p) * w;
        p = ROT2 * p * 2.02;
        a *= 0.5;
    }
    return s;
}

void mainImage(out vec4 fragColor, in vec2 fragCoord) {
    vec2 uv = fragCoord / iResolution.xy;
    vec2 p = (2.0 * fragCoord - iResolution.xy) / iResolution.y * 1.6 + vec2(3.1, 1.7) + iTime * vec2(0.03, 0.01);
    float oc = 1.0 + iStep;
    float h = heightAt(p, oc);
    vec2 e = vec2(0.004, 0.0);
    vec3 n = normalize(vec3(heightAt(p - e.xy, oc) - heightAt(p + e.xy, oc),
                            heightAt(p - e.yx, oc) - heightAt(p + e.yx, oc), 2.0 * e.x * 1.4));
    float hs = clamp(dot(n, normalize(vec3(-0.6, 0.6, 0.55))), 0.0, 1.0);
    float sea = 0.36;
    vec3 col;
    if (h < sea) {
        col = mix(vec3(0.05, 0.16, 0.3), vec3(0.18, 0.42, 0.55), smoothstep(sea - 0.2, sea, h));
    } else {
        float k = (h - sea) / (1.0 - sea);
        col = mix(vec3(0.25, 0.45, 0.2), vec3(0.62, 0.55, 0.35), smoothstep(0.0, 0.35, k));
        col = mix(col, vec3(0.5, 0.42, 0.38), smoothstep(0.35, 0.6, k));
        col = mix(col, vec3(0.95), smoothstep(0.62, 0.75, k));
        col *= 0.45 + 0.75 * hs;
        float c = abs(fract(h * 22.0) - 0.5);                  // contour lines
        col *= 1.0 - 0.35 * smoothstep(0.06, 0.0, c);
    }
    fragColor = vec4(pow(col, vec3(0.95)), 1.0);
}
