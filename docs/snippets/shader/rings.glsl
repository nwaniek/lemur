// Interference of two point sources; each step adds a source, and the eased
// iStep glides the new one in.
void mainImage(out vec4 fragColor, in vec2 fragCoord) {
    vec2 p = (2.0 * fragCoord - iResolution.xy) / iResolution.y;
    float w = 0.0;
    for (int k = 0; k < 4; k++) {
        float on = clamp(iStep + 1.0 - float(k), 0.0, 1.0);          // source k fades in at step k
        float a = 6.2832 * float(k) / 4.0 + 0.2 * iTime;
        vec2 c = 0.55 * vec2(cos(a), sin(a));
        w += on * sin(28.0 * length(p - c) - 4.0 * iTime);
    }
    vec3 col = 0.5 + 0.5 * cos(vec3(0.0, 2.1, 4.2) + 1.2 * w);
    fragColor = vec4(col * (0.35 + 0.65 * smoothstep(-1.0, 3.0, w)), 1.0);
}
