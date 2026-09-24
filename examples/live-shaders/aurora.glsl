// aurora.glsl — polar lights over a frozen lake. Steps: a faint arc, bright
// curtains, a violet corona overhead (the camera tilts up), a substorm.
#include "common.glsl"

// mountain silhouettes as a function of azimuth, two layers
float ridge(float x, float seed) { return fbm2(vec2(x * 2.2 + seed, seed), 5); }

void mainImage(out vec4 fragColor, in vec2 fragCoord) {
    vec2 uv = fragCoord / iResolution.xy;
    vec2 q = (2.0 * fragCoord - iResolution.xy) / iResolution.y;
    float s = iStep;
    float strength = 0.35 + 0.9 * smoothstep(0.0, 1.0, s) + 0.4 * smoothstep(2.0, 3.0, s);
    float speed = 1.0 + 3.0 * smoothstep(2.0, 3.0, s);
    float tilt = 0.08 + 0.55 * smoothstep(1.0, 2.0, s) - 0.25 * smoothstep(2.0, 3.0, s);

    vec3 ro = vec3(0.0, 2.0, 0.0);
    float yaw = 0.15 * sin(iTime * 0.05);
    vec3 ww = normalize(vec3(sin(yaw), tilt, cos(yaw)));
    vec3 uu = normalize(cross(ww, vec3(0.0, 1.0, 0.0)));
    vec3 vv = cross(uu, ww);
    vec3 rd = normalize(q.x * uu + q.y * vv + 1.5 * ww);

    vec3 col;
    bool lake = rd.y < 0.0;
    vec3 d = lake ? vec3(rd.x, -rd.y, rd.z) : rd;       // the lake mirrors the sky
    // sky: deep blue, stars, the aurora
    col = mix(vec3(0.02, 0.04, 0.07), vec3(0.0, 0.005, 0.02), pow(max(d.y, 0.0), 0.4));
    col += stars(d, iTime);
    vec3 au = aurora(ro, d, iTime, strength, speed);
    // the corona: violet at high strength
    au *= mix(vec3(1.0), vec3(1.1, 0.8, 1.3), smoothstep(1.5, 2.5, s));
    col += au;
    // mountains: two ridges against the sky, lit faintly green by the aurora
    float az = atan(d.x, d.z);
    float el = d.y;
    float r1 = 0.05 + 0.12 * ridge(az, 3.1), r2 = 0.02 + 0.07 * ridge(az * 1.7, 9.4);
    vec3 glow = vec3(0.02, 0.08, 0.05) * strength;
    if (el < r1) col = mix(col, vec3(0.012, 0.018, 0.03) + glow * 0.6 + vec3(0.05) * smoothstep(r1 - 0.02, r1, el), 0.97);
    if (el < r2) col = mix(col, vec3(0.006, 0.01, 0.018) + glow * 0.3, 0.98);
    if (lake) {                                          // ice: dark, a little rough
        col *= 0.55 + 0.25 * noise2(vec2(az * 40.0, rd.y * 300.0));
        col += vec3(0.01, 0.02, 0.03) * (1.0 - smoothstep(0.0, 0.2, -rd.y));
    }
    fragColor = vec4(finish(col * 1.2, uv), 1.0);
}
