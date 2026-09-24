// clouds.glsl — volumetric clouds: a slab of fbm "fog", marched with
// Beer–Lambert absorption, a Henyey–Greenstein phase and a powder term.
// Steps: fair weather, towering cumulus, sunset, a thunderstorm.
#include "common.glsl"

const float BASE = 1400.0, TOP = 3600.0;

struct Sky { vec3 sun; vec3 sunCol; vec3 zen; vec3 hor; float cover; float dark; };

Sky skyAt(float s) {
    Sky k;
    float w0 = stage(s, 0.0), w1 = stage(s, 1.0), w2 = stage(s, 2.0), w3 = stage(s, 3.0);
    k.sun = normalize(w0 * vec3(0.3, 0.55, 0.8) + w1 * vec3(-0.2, 0.45, 0.9) + w2 * vec3(0.1, 0.06, 1.0) + w3 * vec3(0.2, 0.3, 0.9));
    k.sunCol = w0 * vec3(1.6, 1.5, 1.35) + w1 * vec3(1.7, 1.55, 1.4) + w2 * vec3(2.0, 0.85, 0.45) + w3 * vec3(0.9, 0.92, 1.0);
    k.zen = w0 * vec3(0.2, 0.42, 0.85) + w1 * vec3(0.18, 0.4, 0.82) + w2 * vec3(0.12, 0.14, 0.38) + w3 * vec3(0.03, 0.035, 0.05);
    k.hor = w0 * vec3(0.7, 0.82, 0.95) + w1 * vec3(0.7, 0.8, 0.92) + w2 * vec3(1.0, 0.55, 0.4) + w3 * vec3(0.09, 0.1, 0.12);
    k.cover = w0 * 0.38 + w1 * 0.58 + w2 * 0.5 + w3 * 0.66;
    k.dark = w3;
    return k;
}

float density(vec3 p, float cover) {
    float h = (p.y - BASE) / (TOP - BASE);
    if (h < 0.0 || h > 1.0) return 0.0;
    vec3 w = vec3(iTime * 12.0, 0.0, iTime * 5.0);
    float base = fbm3((p + w) * 0.00055, 4);
    float detail = fbm3((p + w * 1.6) * 0.0025, 3);
    float shape = smoothstep(0.0, 0.12, h) * smoothstep(1.0, 0.35 + 0.4 * (1.0 - cover), h);
    float d = base - (1.0 - cover) * 0.75 - 0.18 * detail * (1.0 - h);
    return max(d * shape, 0.0) * 0.06;
}

float hg(float c, float g) { return (1.0 - g * g) / (4.0 * PI * pow(1.0 + g * g - 2.0 * g * c, 1.5)); }

void mainImage(out vec4 fragColor, in vec2 fragCoord) {
    vec2 uv = fragCoord / iResolution.xy;
    vec2 q = (2.0 * fragCoord - iResolution.xy) / iResolution.y;
    Sky k = skyAt(iStep);
    vec3 ro = vec3(0.0, 200.0, iTime * 30.0);
    vec3 rd = normalize(vec3(q.x, q.y * 0.9 + 0.32, 1.5));

    vec3 col = mix(k.hor, k.zen, pow(max(rd.y, 0.0), 0.45));
    float sd = max(dot(rd, k.sun), 0.0);
    col += k.sunCol * (0.2 * pow(sd, 8.0) + 3.0 * pow(sd, 700.0)) * (1.0 - k.dark);

    if (rd.y > 0.0) {
        float t0 = (BASE - ro.y) / rd.y, t1 = min((TOP - ro.y) / rd.y, 30000.0);
        float dt = (t1 - t0) / 64.0;
        float t = t0 + dt * hash12(fragCoord + fract(iTime));   // jitter against banding
        float trans = 1.0;
        vec3 light = vec3(0.0);
        float mu = dot(rd, k.sun);
        float phase = mix(hg(mu, 0.6), hg(mu, -0.25), 0.3);
        for (int i = 0; i < 64; i++) {
            vec3 p = ro + rd * t;
            float dens = density(p, k.cover);
            if (dens > 0.0005) {
                float sh = 0.0;                                       // optical depth toward the sun
                for (int j = 1; j <= 5; j++) sh += density(p + k.sun * 150.0 * float(j), k.cover);
                float beer = exp(-sh * 150.0 * 1.4);
                float powder = 1.0 - exp(-dens * 300.0);
                vec3 lum = k.sunCol * beer * powder * phase * 9.0 * (1.0 - 0.55 * k.dark)
                         + mix(k.hor, k.zen, 0.5) * 0.45 + k.dark * vec3(0.05, 0.055, 0.07);
                float a = 1.0 - exp(-dens * dt);
                light += trans * a * lum;
                trans *= 1.0 - a;
                if (trans < 0.01) break;
            }
            t += dt;
        }
        // lightning: a random flash inside the storm
        float bolt = floor(iTime * 6.0);
        float flash = k.dark * step(0.975, hash12(vec2(bolt, 3.0)));
        vec2 at = vec2(hash12(vec2(bolt, 1.0)), hash12(vec2(bolt, 2.0))) * 2.0 - 1.0;   // where it strikes
        light += flash * (1.0 - trans) * vec3(0.8, 0.85, 1.2) * 2.2 * exp(-3.0 * length(q - at * vec2(1.4, 0.4)));
        float fade = exp(-t0 * 0.00006);
        col = mix(col, light + col * trans, fade);
    } else {                                                              // distant land
        col = mix(k.hor * 0.35, k.zen * 0.25, clamp(-rd.y * 4.0, 0.0, 1.0)) * (1.0 - 0.6 * k.dark);
    }
    col = mix(col, k.hor, exp(-abs(rd.y) * 18.0) * 0.5);                 // haze at the horizon
    fragColor = vec4(finish(col, uv), 1.0);
}
