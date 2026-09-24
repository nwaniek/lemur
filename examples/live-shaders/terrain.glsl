// terrain.glsl — a flyover of an eroded, raymarched landscape (a homage to
// "Elevated" by Rgba & TBC, 2009). Four lighting stages — dawn, day, dusk and a
// night with stars and polar lights — blend as the slide steps (iStep).
#include "common.glsl"

#ifndef START_STAGE
#define START_STAGE 0.0
#endif

const float WATER = 38.0;

// height: fbm whose octaves are damped where the slope is steep (IQ's
// "derivative erosion") — ridges and gullies instead of blobby hills
float terrainH(vec2 x, int oct) {
    vec2 p = x * 0.0032;
    float a = 0.0, b = 1.0;
    vec2 d = vec2(0.0);
    for (int i = 0; i < 12; i++) {
        if (i >= oct) break;
        vec3 n = noised(p);
        d += n.yz;
        a += b * n.x / (1.0 + dot(d, d));
        b *= 0.5;
        p = ROT2 * p * 2.0;
    }
    return 130.0 * a;
}

vec3 terrainN(vec3 p, float t) {
    vec2 e = vec2(max(0.02, 0.0015 * t), 0.0);
    return normalize(vec3(terrainH(p.xz - e.xy, 11) - terrainH(p.xz + e.xy, 11), 2.0 * e.x,
                          terrainH(p.xz - e.yx, 11) - terrainH(p.xz + e.yx, 11)));
}

float march(vec3 ro, vec3 rd, float tmax) {
    float t = 1.0;
    for (int i = 0; i < 300; i++) {
        vec3 p = ro + rd * t;
        float h = p.y - terrainH(p.xz, 8);
        if (abs(h) < 0.0015 * t || t > tmax) break;
        t += 0.45 * h;
    }
    return t;
}

float softShadow(vec3 ro, vec3 rd) {
    float res = 1.0, t = 2.0;
    for (int i = 0; i < 40; i++) {
        vec3 p = ro + rd * t;
        float h = p.y - terrainH(p.xz, 6);
        res = min(res, 12.0 * h / t);
        t += clamp(h, 2.0, 40.0);
        if (res < 0.001 || p.y > 260.0) break;
    }
    return clamp(res, 0.0, 1.0);
}

// -- the four stages --------------------------------------------------------------
struct Env { vec3 sun; vec3 sunCol; vec3 top; vec3 hor; vec3 fog; float night; };

Env env(int k) {
    Env e;
    if (k == 0) {            // dawn
        e.sun = normalize(vec3(-0.8, 0.12, 0.6)); e.sunCol = vec3(1.6, 0.95, 0.55);
        e.top = vec3(0.25, 0.35, 0.6); e.hor = vec3(1.0, 0.72, 0.55); e.fog = vec3(0.85, 0.7, 0.62); e.night = 0.0;
    } else if (k == 1) {     // day
        e.sun = normalize(vec3(-0.3, 0.7, 0.5)); e.sunCol = vec3(1.7, 1.55, 1.35);
        e.top = vec3(0.22, 0.45, 0.85); e.hor = vec3(0.68, 0.8, 0.95); e.fog = vec3(0.62, 0.72, 0.85); e.night = 0.0;
    } else if (k == 2) {     // dusk
        e.sun = normalize(vec3(0.85, 0.07, 0.55)); e.sunCol = vec3(1.9, 0.6, 0.35);
        e.top = vec3(0.16, 0.12, 0.35); e.hor = vec3(1.0, 0.45, 0.35); e.fog = vec3(0.55, 0.35, 0.42); e.night = 0.0;
    } else {                 // night
        e.sun = normalize(vec3(0.2, 0.45, -0.8)); e.sunCol = vec3(0.06, 0.08, 0.13);   // moonlight
        e.top = vec3(0.005, 0.01, 0.03); e.hor = vec3(0.02, 0.05, 0.08); e.fog = vec3(0.02, 0.04, 0.06); e.night = 1.0;
    }
    return e;
}

Env envAt(float s) {
    s = clamp(s, 0.0, 3.0);
    int k0 = int(floor(s));
    int k1 = min(k0 + 1, 3);
    float f = smoothstep(0.0, 1.0, s - float(k0));
    Env a = env(k0), b = env(k1), e;
    e.sun = normalize(mix(a.sun, b.sun, f)); e.sunCol = mix(a.sunCol, b.sunCol, f);
    e.top = mix(a.top, b.top, f); e.hor = mix(a.hor, b.hor, f); e.fog = mix(a.fog, b.fog, f);
    e.night = mix(a.night, b.night, f);
    return e;
}

vec3 sky(vec3 ro, vec3 rd, Env e) {
    float y = max(rd.y, 0.0);
    vec3 c = mix(e.hor, e.top, pow(y, 0.5));
    float sd = max(dot(rd, e.sun), 0.0);
    c += e.sunCol * (0.25 * pow(sd, 6.0) + 0.6 * pow(sd, 64.0) + 3.0 * pow(sd, 900.0)) * (1.0 - e.night);
    if (rd.y > 0.0) {                              // a thin deck of high clouds
        vec2 cp = rd.xz / (rd.y + 0.05) * 0.9 + iTime * 0.015;
        float cl = smoothstep(0.5, 0.85, fbm2(cp, 6));
        vec3 cc = mix(e.hor * 1.15, e.sunCol * 0.7 + e.hor * 0.5, pow(sd, 3.0));
        c = mix(c, cc * (1.0 - 0.85 * e.night), cl * 0.6 * smoothstep(0.0, 0.2, rd.y));
    }
    c += e.night * stars(rd, iTime);
    c += e.night * aurora(ro, rd, iTime, 1.1, 1.0);
    return c;
}

vec3 shade(vec3 p, vec3 n, float t, Env e) {
    float slope = n.y;
    vec3 rock = mix(vec3(0.24, 0.2, 0.17), vec3(0.36, 0.3, 0.25), noise2(p.xz * 0.05));
    vec3 grass = vec3(0.13, 0.18, 0.08);
    vec3 col = mix(rock, grass, smoothstep(0.78, 0.92, slope) * smoothstep(105.0, 70.0, p.y));
    float snow = smoothstep(105.0, 125.0, p.y + 25.0 * fbm2(p.xz * 0.015, 3)) * smoothstep(0.55, 0.8, slope);
    col = mix(col, vec3(0.92, 0.95, 1.0), snow);
    col = mix(col, vec3(0.45, 0.4, 0.3), smoothstep(WATER + 3.0, WATER, p.y));      // shore sand
    float dif = max(dot(n, e.sun), 0.0);
    float sh = dif > 0.0 ? softShadow(p + n * 0.5, e.sun) : 0.0;
    vec3 lin = dif * sh * e.sunCol * 2.4;
    lin += (0.55 + 0.45 * n.y) * e.top * 1.1;                                          // sky light
    lin += max(0.0, dot(n, normalize(vec3(-e.sun.x, 0.0, -e.sun.z)))) * e.hor * 0.25;  // bounce
    lin += e.night * vec3(0.01, 0.05, 0.03) * (0.5 + 0.5 * n.y);                       // aurora glow
    return col * lin * (1.0 - 0.55 * e.night);
}

vec3 camPath(float z) { return vec3(160.0 * sin(z * 0.0021) + 60.0 * sin(z * 0.0053), 0.0, z); }

void mainImage(out vec4 fragColor, in vec2 fragCoord) {
    vec2 uv = fragCoord / iResolution.xy;
    vec2 q = (2.0 * fragCoord - iResolution.xy) / iResolution.y;
    Env e = envAt(iStep + START_STAGE);

    float z = iTime * 22.0 + 1200.0;
    vec3 ro = camPath(z);
    // fly over whatever lies ahead: a smooth maximum of the terrain in front
    float acc = 0.0;
    for (int i = 0; i < 8; i++) acc += exp(0.06 * max(terrainH(camPath(z + float(i) * 45.0).xz, 4), WATER));
    ro.y = log(acc / 8.0) / 0.06 + 45.0;
    vec3 ta = camPath(z + 140.0);
    ta.y = ro.y - 42.0;
    vec3 ww = normalize(ta - ro);
    vec3 uu = normalize(cross(ww, vec3(0.0, 1.0, 0.0)));
    vec3 vv = cross(uu, ww);
    float roll = 0.12 * sin(z * 0.004);
    vec3 rd = normalize(q.x * (uu * cos(roll) + vv * sin(roll)) + q.y * (vv * cos(roll) - uu * sin(roll)) + 1.6 * ww);

    const float TMAX = 3200.0;
    float t = march(ro, rd, TMAX);
    float tw = rd.y < 0.0 ? (WATER - ro.y) / rd.y : 1e9;
    vec3 col;
    if (tw < t && tw < TMAX) {                    // the lake: fresnel mix of sky and depth
        vec3 p = ro + rd * tw;
        vec2 rip = vec2(fbm2(p.xz * 0.08 + iTime * 0.3, 3), fbm2(p.xz * 0.08 - iTime * 0.25 + 5.0, 3)) - 0.5;
        vec3 n = normalize(vec3(rip.x * 0.12, 1.0, rip.y * 0.12));
        vec3 rr = reflect(rd, n);
        float fre = 0.04 + 0.96 * pow(1.0 - max(dot(-rd, n), 0.0), 5.0);
        col = mix(vec3(0.01, 0.03, 0.04) + e.top * 0.05, sky(ro, rr, e), fre);
        t = tw;
    } else if (t < TMAX) {
        vec3 p = ro + rd * t;
        col = shade(p, terrainN(p, t), t, e);
    } else {
        col = sky(ro, rd, e);
    }
    // aerial perspective: fog tinted toward the sun
    float sd = max(dot(rd, e.sun), 0.0);
    vec3 fogc = mix(e.fog, e.sunCol * 0.9, pow(sd, 8.0) * (1.0 - e.night));
    col = mix(col, fogc, 1.0 - exp(-min(t, TMAX) * 0.0008));
    fragColor = vec4(finish(col * 0.95, uv), 1.0);
}
