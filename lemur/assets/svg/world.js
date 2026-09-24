/* World shapes for lemur SVG decks — the twin of lemur/anim/world.py (keep the
 * two in step; tests/python/test_anim.py runs both on the same cases).
 *
 * A 3-D shape made through a lemur.anim View ships its world geometry and a
 * rule; the !anim player (runtime.js) projects it with its view's camera at
 * time t: `poly` (rules cull / vis / hid), `anchor` (a 2-D outline placed at a
 * projected point; hide / ghost), `limb` / `base` (the occluder's outline).
 * Inlined only into decks that have world shapes. */
(function () {
  function fnum(x) { return Math.round(x * 10000) / 10000; }
  var LMRW = {
    toward: function (c) {
      return [-Math.sin(c.a) * Math.cos(c.e), -Math.cos(c.a) * Math.cos(c.e), Math.sin(c.e)];
    },
    project: function (c, x, y, z) {
      x -= c.o[0]; y -= c.o[1]; z -= c.o[2];
      var ca = Math.cos(c.a), sa = Math.sin(c.a), se = Math.sin(c.e), ce = Math.cos(c.e);
      var sx = ca * x - sa * y, sy = (sa * x + ca * y) * se + z * ce;
      if (c.p !== null && c.p !== undefined) {
        var dc = z * se - (sa * x + ca * y) * ce, k = c.p / Math.max(c.p - dc, 1e-3);
        sx *= k; sy *= k;
      }
      return [sx * c.s + c.c[0], sy * c.s + c.c[1]];
    },
    occludes: function (occ, c, x, y, z) {
      if (!occ) return false;
      var d = LMRW.toward(c), R = occ.R;
      x -= occ.c[0]; y -= occ.c[1]; z -= occ.c[2];
      var b = x * d[0] + y * d[1] + z * d[2], disc = b * b - (x * x + y * y + z * z - R * R);
      if (disc <= 0) return false;
      var rt = Math.sqrt(disc), ss = [-b - rt, -b + rt];   // 1e-2: world.SURFACE_EPS
      for (var i = 0; i < 2; i++) {
        var s = ss[i];
        if (s > 1e-2 * R && (occ.cap === null || occ.cap === undefined ||
                              z + s * d[2] + occ.c[2] >= occ.cap - 1e-6)) return true;
      }
      return false;
    },
    runs: function (flags, closed) {
      var n = flags.length, out = [], i, k;
      if (!n) return out;
      var all = true, none = true;
      for (i = 0; i < n; i++) { if (flags[i]) none = false; else all = false; }
      if (all || none) {
        var idx = []; for (i = 0; i < n; i++) idx.push(i);
        if (closed) idx.push(0);
        return [[flags[0], idx]];
      }
      var start = 0;
      if (closed) for (i = 0; i < n; i++) if (flags[i] !== flags[(i + n - 1) % n]) { start = i; break; }
      for (k = 0; k < n; k++) {
        i = closed ? (start + k) % n : k;
        if (out.length && out[out.length - 1][0] === flags[i]) out[out.length - 1][1].push(i);
        else out.push([flags[i], [i]]);
      }
      return out;
    },
    split: function (occ, c, P, off, n, closed, want) {
      var flags = [];
      for (var i = 0; i < n; i++) { var b = 3 * (off + i); flags.push(!LMRW.occludes(occ, c, P[b], P[b + 1], P[b + 2])); }
      var rs = LMRW.runs(flags, closed), out = [];
      for (var k = 0; k < rs.length; k++) {
        var vis = rs[k][0], idx = rs[k][1];
        if (vis !== want) continue;
        if (!vis && rs.length > 1) {
          if (k > 0 || closed) { var pr = rs[(k + rs.length - 1) % rs.length][1]; idx = [pr[pr.length - 1]].concat(idx); }
          if (k + 1 < rs.length || closed) idx = idx.concat([rs[(k + 1) % rs.length][1][0]]);
        }
        if (idx.length >= 2) out.push(idx);
      }
      return out;
    },
    circle: function (occ, c, limb, n) {        // limb: silhouette; else a dome's front base
      var d = LMRW.toward(c), out = [], i, t;
      if (limb) {
        var u = [d[1], -d[0], 0], un = Math.hypot(u[0], u[1]) || 1;
        u = [u[0] / un, u[1] / un, 0];
        var w = [d[1] * u[2] - d[2] * u[1], d[2] * u[0] - d[0] * u[2], d[0] * u[1] - d[1] * u[0]];
        if (w[2] < 0) w = [-w[0], -w[1], -w[2]];
        var span = (occ.cap === null || occ.cap === undefined) ? 2 * Math.PI : Math.PI;
        for (i = 0; i < n; i++) {
          t = span * i / (n - 1);
          out.push(LMRW.project(c, occ.c[0] + occ.R * (Math.cos(t) * u[0] + Math.sin(t) * w[0]),
                                   occ.c[1] + occ.R * (Math.cos(t) * u[1] + Math.sin(t) * w[1]),
                                   occ.c[2] + occ.R * (Math.cos(t) * u[2] + Math.sin(t) * w[2])));
        }
        return out;
      }
      var h = occ.cap - occ.c[2], rb = Math.sqrt(Math.max(occ.R * occ.R - h * h, 0)), f = Math.atan2(d[1], d[0]);
      for (i = 0; i < n; i++) {
        t = -Math.PI / 2 + Math.PI * i / (n - 1) + f;
        out.push(LMRW.project(c, occ.c[0] + rb * Math.cos(t), occ.c[1] + rb * Math.sin(t), occ.cap));
      }
      return out;
    },
    // The 2-D polylines [[pts…], closed] a world shape draws for camera c.
    paths: function (kind, rule, occ, c, P, struct) {
      if (kind === 'limb') return occ ? [[LMRW.circle(occ, c, true, 90), false]] : [];
      if (kind === 'base') return occ && occ.cap !== null && occ.cap !== undefined ? [[LMRW.circle(occ, c, false, 60), false]] : [];
      var out = [], counts = struct[0], closed = struct[1], off = 0, i, j;
      for (var q = 0; q < counts.length; q++) {
        var n = counts[q], cl = !!closed[q];
        if (rule === 'vis' || rule === 'hid') {
          var parts = LMRW.split(occ, c, P, off, n, cl, rule === 'vis');
          for (j = 0; j < parts.length; j++) {
            var pl = [];
            for (i = 0; i < parts[j].length; i++) { var b = 3 * (off + parts[j][i]); pl.push(LMRW.project(c, P[b], P[b + 1], P[b + 2])); }
            out.push([pl, false]);
          }
        } else {
          var all = [];
          for (i = 0; i < n; i++) { var e = 3 * (off + i); all.push(LMRW.project(c, P[e], P[e + 1], P[e + 2])); }
          out.push([all, cl]);
        }
        off += n;
      }
      return out;
    },
    d: function (polys) {
      var s = '', L = 0;
      for (var q = 0; q < polys.length; q++) {
        var pl = polys[q][0];
        for (var j = 0; j < pl.length; j++) {
          s += (j ? 'L' : 'M') + fnum(pl[j][0]) + ',' + fnum(pl[j][1]);
          if (j) L += Math.hypot(pl[j][0] - pl[j - 1][0], pl[j][1] - pl[j - 1][1]);
        }
        if (pl.length && polys[q][1]) { s += 'Z'; L += Math.hypot(pl[0][0] - pl[pl.length - 1][0], pl[0][1] - pl[pl.length - 1][1]); }
      }
      return [s, L];
    }
  };
  window.LMRW = LMRW;
})();
