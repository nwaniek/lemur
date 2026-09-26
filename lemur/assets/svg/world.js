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
      if (occ.meshes) return LMRW.meshOccluded(occ, c, x, y, z);
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

  /* ---- meshes (twin of the mesh half of world.py) ---------------------------
   * GPU views: surfaces of flat faces that hide what is behind them. A point is
   * hidden when an occluding triangle covers it on screen and is nearer (by more
   * than eps); a grid over the screen keeps that test cheap. */
  var MESH_EPS = 2e-2, CONTOUR_EPS_SCALE = 4.0;

  LMRW.depth = function (c, x, y, z) {
    var t = LMRW.toward(c);
    return (x - c.o[0]) * t[0] + (y - c.o[1]) * t[1] + (z - c.o[2]) * t[2];
  };
  LMRW.eyeDir = function (c, x, y, z) {
    var t = LMRW.toward(c);
    if (c.p === null || c.p === undefined) return t;
    var ex = c.o[0] + c.p * t[0] - x, ey = c.o[1] + c.p * t[1] - y, ez = c.o[2] + c.p * t[2] - z;
    var n = Math.hypot(ex, ey, ez) || 1e-12;
    return [ex / n, ey / n, ez / n];
  };

  // topology: triangles (fan), vertices welded by position, the open boundary
  LMRW.meshGeo = function (P, faces, k) {
    var N = P.length / 3, F = faces.length / k, i, j;
    var tris = [];
    for (i = 0; i < F; i++) for (j = 1; j < k - 1; j++) tris.push(faces[i * k], faces[i * k + j], faces[i * k + j + 1]);
    var scale = 1e-9;
    for (i = 0; i < P.length; i++) scale = Math.max(scale, Math.abs(P[i]));
    var ids = new Int32Array(N), keys = {}, next = 0;
    for (i = 0; i < N; i++) {
      var key = Math.round(P[3 * i] / scale * 1e7) + ',' + Math.round(P[3 * i + 1] / scale * 1e7) + ',' +
                Math.round(P[3 * i + 2] / scale * 1e7);
      if (!(key in keys)) keys[key] = next++;
      ids[i] = keys[key];
    }
    var count = {}, first = {};
    for (i = 0; i < F; i++) for (j = 0; j < k; j++) {
      var a = faces[i * k + j], b = faces[i * k + (j + 1) % k];
      var ia = ids[a], ib = ids[b], ek = ia < ib ? ia + ',' + ib : ib + ',' + ia;
      count[ek] = (count[ek] || 0) + 1;
      if (!(ek in first)) first[ek] = [a, b];
    }
    var boundary = [];
    for (var ek2 in count) if (count[ek2] === 1) {
      var e = first[ek2];
      if (ids[e[0]] !== ids[e[1]]) boundary.push(e);
    }
    return { faces: faces, k: k, tris: new Int32Array(tris), ids: ids, nids: next, boundary: boundary };
  };

  LMRW.vertexNormals = function (P, geo) {
    var t = geo.tris, acc = new Float64Array(3 * geo.nids), i, j;
    for (i = 0; i < t.length; i += 3) {
      var a = 3 * t[i], b = 3 * t[i + 1], c = 3 * t[i + 2];
      var ux = P[b] - P[a], uy = P[b + 1] - P[a + 1], uz = P[b + 2] - P[a + 2];
      var vx = P[c] - P[a], vy = P[c + 1] - P[a + 1], vz = P[c + 2] - P[a + 2];
      var nx = uy * vz - uz * vy, ny = uz * vx - ux * vz, nz = ux * vy - uy * vx;
      for (j = 0; j < 3; j++) { var w = 3 * geo.ids[t[i + j]]; acc[w] += nx; acc[w + 1] += ny; acc[w + 2] += nz; }
    }
    var N = P.length / 3, vn = new Float64Array(3 * N);
    for (i = 0; i < N; i++) {
      var q = 3 * geo.ids[i], n = Math.hypot(acc[q], acc[q + 1], acc[q + 2]) || 1e-12;
      vn[3 * i] = acc[q] / n; vn[3 * i + 1] = acc[q + 1] / n; vn[3 * i + 2] = acc[q + 2] / n;
    }
    return vn;
  };

  // the outline for camera c: smooth silhouette + open boundary, as 3-D polylines
  LMRW.contour = function (c, P, geo, vn) {
    vn = vn || LMRW.vertexNormals(P, geo);
    var N = P.length / 3, f = new Float64Array(N), i, ids = geo.ids;
    for (i = 0; i < N; i++) {
      var e = LMRW.eyeDir(c, P[3 * i], P[3 * i + 1], P[3 * i + 2]);
      f[i] = vn[3 * i] * e[0] + vn[3 * i + 1] * e[1] + vn[3 * i + 2] * e[2];
    }
    var pts = {}, segs = [], t = geo.tris;
    for (i = 0; i < t.length; i += 3) {
      var cross = [], ed = [[t[i], t[i + 1]], [t[i + 1], t[i + 2]], [t[i + 2], t[i]]];
      for (var q = 0; q < 3; q++) {
        var a = ed[q][0], b = ed[q][1];
        if ((f[a] >= 0) !== (f[b] >= 0) && ids[a] !== ids[b]) {
          var key = ids[a] < ids[b] ? ids[a] + ',' + ids[b] : ids[b] + ',' + ids[a];
          if (!(key in pts)) {
            var w = f[a] / (f[a] - f[b]);
            pts[key] = [P[3 * a] + w * (P[3 * b] - P[3 * a]), P[3 * a + 1] + w * (P[3 * b + 1] - P[3 * a + 1]),
                        P[3 * a + 2] + w * (P[3 * b + 2] - P[3 * a + 2])];
          }
          cross.push(key);
        }
      }
      if (cross.length === 2) segs.push(cross);
    }
    geo.boundary.forEach(function (e) {
      var ka = 'v' + ids[e[0]], kb = 'v' + ids[e[1]];
      if (!(ka in pts)) pts[ka] = [P[3 * e[0]], P[3 * e[0] + 1], P[3 * e[0] + 2]];
      if (!(kb in pts)) pts[kb] = [P[3 * e[1]], P[3 * e[1] + 1], P[3 * e[1] + 2]];
      segs.push([ka, kb]);
    });
    return LMRW.chain(segs).map(function (keys) { return keys.map(function (k) { return pts[k]; }); });
  };

  LMRW.chain = function (segs) {
    var adj = {}, used = new Array(segs.length), out = [], i;
    segs.forEach(function (sg, i) { (adj[sg[0]] = adj[sg[0]] || []).push(i); (adj[sg[1]] = adj[sg[1]] || []).push(i); });
    function walk(si, start) {
      var keys = [start], cur = start;
      for (;;) {
        used[si] = true;
        var nxt = segs[si][0] === cur ? segs[si][1] : segs[si][0];
        keys.push(nxt);
        var cand = adj[nxt].filter(function (j) { return !used[j]; });
        if (!cand.length) return keys;
        si = cand[0]; cur = nxt;
      }
    }
    for (var k in adj) if (adj[k].length === 1) adj[k].forEach(function (j) { if (!used[j]) out.push(walk(j, k)); });
    for (i = 0; i < segs.length; i++) if (!used[i]) out.push(walk(i, segs[i][0]));
    return out;
  };

  LMRW.meshOccluder = function (P, geo) {
    var lo = [Infinity, Infinity, Infinity], hi = [-Infinity, -Infinity, -Infinity];
    for (var i = 0; i < P.length; i += 3) for (var j = 0; j < 3; j++) {
      lo[j] = Math.min(lo[j], P[i + j]); hi[j] = Math.max(hi[j], P[i + j]);
    }
    var r = Math.hypot(hi[0] - lo[0], hi[1] - lo[1], hi[2] - lo[2]) / 2;
    return { P: P, tris: geo.tris, eps: MESH_EPS * Math.max(r, 1e-9) };
  };
  LMRW.contourOccluder = function (occ) {
    if (!occ || !occ.meshes) return occ;
    return { meshes: occ.meshes.map(function (m) { return { P: m.P, tris: m.tris, eps: m.eps * CONTOUR_EPS_SCALE }; }) };
  };

  // the screen grid of one occluding mesh for camera c (cached per camera)
  function occGrid(m, c) {
    var key = [c.a, c.e, c.s, c.c[0], c.c[1], c.p].join(',');
    if (m._key === key) return m._grid;
    var P = m.P, N = P.length / 3, xy = new Float64Array(2 * N), dz = new Float64Array(N), i;
    var lx = Infinity, ly = Infinity, hx = -Infinity, hy = -Infinity;
    for (i = 0; i < N; i++) {
      var q = LMRW.project(c, P[3 * i], P[3 * i + 1], P[3 * i + 2]);
      xy[2 * i] = q[0]; xy[2 * i + 1] = q[1]; dz[i] = LMRW.depth(c, P[3 * i], P[3 * i + 1], P[3 * i + 2]);
      lx = Math.min(lx, q[0]); ly = Math.min(ly, q[1]); hx = Math.max(hx, q[0]); hy = Math.max(hy, q[1]);
    }
    var G = 48, cw = Math.max(hx - lx, 1e-9) / G, ch = Math.max(hy - ly, 1e-9) / G, cells = new Array(G * G);
    var t = m.tris;
    for (i = 0; i < t.length; i += 3) {
      var a = t[i], b = t[i + 1], d = t[i + 2];
      var x0 = Math.min(xy[2 * a], xy[2 * b], xy[2 * d]), x1 = Math.max(xy[2 * a], xy[2 * b], xy[2 * d]);
      var y0 = Math.min(xy[2 * a + 1], xy[2 * b + 1], xy[2 * d + 1]), y1 = Math.max(xy[2 * a + 1], xy[2 * b + 1], xy[2 * d + 1]);
      var tol = 1e-9 * G * Math.max(cw, ch);              // no cracks at seams
      var i0 = Math.max(0, Math.floor((x0 - tol - lx) / cw)), i1 = Math.min(G - 1, Math.floor((x1 + tol - lx) / cw));
      var j0 = Math.max(0, Math.floor((y0 - tol - ly) / ch)), j1 = Math.min(G - 1, Math.floor((y1 + tol - ly) / ch));
      for (var jj = j0; jj <= j1; jj++) for (var ii = i0; ii <= i1; ii++) (cells[jj * G + ii] = cells[jj * G + ii] || []).push(i);
    }
    m._key = key;
    m._grid = { xy: xy, dz: dz, lx: lx, ly: ly, cw: cw, ch: ch, G: G, cells: cells };
    return m._grid;
  }

  LMRW.meshOccluded = function (occ, c, x, y, z) {
    var p = LMRW.project(c, x, y, z), dp = LMRW.depth(c, x, y, z);
    for (var mi = 0; mi < occ.meshes.length; mi++) {
      var m = occ.meshes[mi], g = occGrid(m, c);
      var ii = Math.floor((p[0] - g.lx) / g.cw), jj = Math.floor((p[1] - g.ly) / g.ch);
      if (ii < 0 || jj < 0 || ii >= g.G || jj >= g.G) {
        if (ii === g.G) ii = g.G - 1; else if (jj === g.G) jj = g.G - 1; else continue;
        if (ii < 0 || jj < 0 || ii >= g.G || jj >= g.G) continue;
      }
      var list = g.cells[jj * g.G + ii];
      if (!list) continue;
      for (var q = 0; q < list.length; q++) {
        var i = list[q], a = m.tris[i], b = m.tris[i + 1], d = m.tris[i + 2], xy = g.xy;
        var ax = xy[2 * a], ay = xy[2 * a + 1], bx = xy[2 * b], by = xy[2 * b + 1], cx = xy[2 * d], cy = xy[2 * d + 1];
        var area = (bx - ax) * (cy - ay) - (by - ay) * (cx - ax);
        if (Math.abs(area) <= 1e-12) continue;
        var l1 = ((cx - bx) * (p[1] - by) - (cy - by) * (p[0] - bx)) / area;
        var l2 = ((ax - cx) * (p[1] - cy) - (ay - cy) * (p[0] - cx)) / area;
        var l3 = 1 - l1 - l2;
        if (l1 < -1e-9 || l2 < -1e-9 || l3 < -1e-9) continue;
        if (l1 * g.dz[a] + l2 * g.dz[b] + l3 * g.dz[d] > dp + m.eps) return true;
      }
    }
    return false;
  };

  function faceNormal(P, f, k, i) {
    var q = function (j) { return 3 * f[i * k + j]; };
    var nx, ny, nz, ux, uy, uz, vx, vy, vz;
    if (k >= 4) {
      ux = P[q(2)] - P[q(0)]; uy = P[q(2) + 1] - P[q(0) + 1]; uz = P[q(2) + 2] - P[q(0) + 2];
      vx = P[q(3)] - P[q(1)]; vy = P[q(3) + 1] - P[q(1) + 1]; vz = P[q(3) + 2] - P[q(1) + 2];
      nx = uy * vz - uz * vy; ny = uz * vx - ux * vz; nz = ux * vy - uy * vx;
      if (Math.hypot(nx, ny, nz) >= 1e-12) return [nx, ny, nz];
      ux = P[q(1)] - P[q(0)]; uy = P[q(1) + 1] - P[q(0) + 1]; uz = P[q(1) + 2] - P[q(0) + 2];
      vx = P[q(3)] - P[q(0)]; vy = P[q(3) + 1] - P[q(0) + 1]; vz = P[q(3) + 2] - P[q(0) + 2];
    } else {
      ux = P[q(1)] - P[q(0)]; uy = P[q(1) + 1] - P[q(0) + 1]; uz = P[q(1) + 2] - P[q(0) + 2];
      vx = P[q(2)] - P[q(0)]; vy = P[q(2) + 1] - P[q(0) + 1]; vz = P[q(2) + 2] - P[q(0) + 2];
    }
    return [uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx];
  }
  LMRW.faceNormal = faceNormal;

  // the faces to draw, far to near: [[face index, depth, [[x, y] …]]]
  LMRW.painterFaces = function (c, P, geo, cull) {
    var f = geo.faces, k = geo.k, F = f.length / k, out = [], i, j;
    for (i = 0; i < F; i++) {
      var cx = 0, cy = 0, cz = 0;
      for (j = 0; j < k; j++) { var b = 3 * f[i * k + j]; cx += P[b]; cy += P[b + 1]; cz += P[b + 2]; }
      cx /= k; cy /= k; cz /= k;
      if (cull) {
        var n = faceNormal(P, f, k, i), e = LMRW.eyeDir(c, cx, cy, cz);
        if (!(n[0] * e[0] + n[1] * e[1] + n[2] * e[2] > 0)) continue;
      }
      out.push([i, LMRW.depth(c, cx, cy, cz)]);
    }
    out.sort(function (a, b) { return a[1] - b[1] || a[0] - b[0]; });
    return out.map(function (fd) {
      var pts = [];
      for (j = 0; j < k; j++) { var b = 3 * f[fd[0] * k + j]; pts.push(LMRW.project(c, P[b], P[b + 1], P[b + 2])); }
      return [fd[0], fd[1], pts];
    });
  };

  function hex(c) {
    var h = function (v) { var n = Math.round(Math.max(0, Math.min(1, v)) * 255).toString(16); return n.length < 2 ? '0' + n : n; };
    return '#' + h(c[0]) + h(c[1]) + h(c[2]);
  }
  function path2(pts, closed) {
    var s = '';
    for (var i = 0; i < pts.length; i++) s += (i ? 'L' : 'M') + fnum(pts[i][0]) + ',' + fnum(pts[i][1]);
    return s + (closed ? 'Z' : '');
  }
  LMRW.trim3 = function (P, closed, a, b) {            // a 3-D polyline between arc-length fractions
    P = closed ? P.concat([P[0]]) : P;
    if ((a <= 1e-4 && b >= 0.9999) || P.length < 2) return P;
    var cum = [0], i;
    for (i = 1; i < P.length; i++) cum.push(cum[i - 1] + Math.hypot(P[i][0] - P[i - 1][0], P[i][1] - P[i - 1][1], P[i][2] - P[i - 1][2]));
    var L = cum[cum.length - 1] || 1, t0 = Math.max(0, Math.min(L, a * L)), t1 = Math.max(0, Math.min(L, b * L));
    var at = function (t) {
      for (var j = 1; j < P.length; j++) if (cum[j] >= t) {
        var w = (t - cum[j - 1]) / ((cum[j] - cum[j - 1]) || 1);
        return [P[j - 1][0] + w * (P[j][0] - P[j - 1][0]), P[j - 1][1] + w * (P[j][1] - P[j - 1][1]), P[j - 1][2] + w * (P[j][2] - P[j - 1][2])];
      }
      return P[P.length - 1];
    };
    var out = [at(t0)];
    for (i = 0; i < P.length; i++) if (cum[i] > t0 && cum[i] < t1) out.push(P[i]);
    out.push(at(t1));
    return out;
  };

  // a node's 3-D polylines ([[pts, closed]]) at its current values
  LMRW.nodePolys = function (node, val, cam, occ, meshes) {
    var wk = node.wk;
    if (wk === 'poly') {
      var flat = val(node, 'p3') || [], st = node.struct || [[], []], off = 0, out = [];
      for (var q = 0; q < st[0].length; q++) {
        var pts = [];
        for (var i = 0; i < st[0][q]; i++) { var b = 3 * (off + i); pts.push([flat[b], flat[b + 1], flat[b + 2]]); }
        out.push([pts, !!st[1][q]]);
        off += st[0][q];
      }
      return out;
    }
    if (wk === 'contour') {
      var m = meshes[node.src];
      return m ? LMRW.contour(cam, m.P, m.geo).map(function (L) { return [L, false]; }) : [];
    }
    if ((wk === 'limb' || wk === 'base') && occ && !occ.meshes) {
      return [[LMRW.circle3(occ, cam, wk === 'limb', wk === 'limb' ? 90 : 60), false]];
    }
    return [];
  };

  LMRW.circle3 = function (occ, c, limb, n) {           // like circle(), in 3-D
    var d = LMRW.toward(c), out = [], i, t;
    if (limb) {
      var u = [d[1], -d[0], 0], un = Math.hypot(u[0], u[1]) || 1;
      u = [u[0] / un, u[1] / un, 0];
      var w = [d[1] * u[2] - d[2] * u[1], d[2] * u[0] - d[0] * u[2], d[0] * u[1] - d[1] * u[0]];
      if (w[2] < 0) w = [-w[0], -w[1], -w[2]];
      var span = (occ.cap === null || occ.cap === undefined) ? 2 * Math.PI : Math.PI;
      for (i = 0; i < n; i++) {
        t = span * i / (n - 1);
        out.push([occ.c[0] + occ.R * (Math.cos(t) * u[0] + Math.sin(t) * w[0]),
                  occ.c[1] + occ.R * (Math.cos(t) * u[1] + Math.sin(t) * w[1]),
                  occ.c[2] + occ.R * (Math.cos(t) * u[2] + Math.sin(t) * w[2])]);
      }
      return out;
    }
    var h = occ.cap - occ.c[2], rb = Math.sqrt(Math.max(occ.R * occ.R - h * h, 0)), f = Math.atan2(d[1], d[0]);
    for (i = 0; i < n; i++) {
      t = -Math.PI / 2 + Math.PI * i / (n - 1) + f;
      out.push([occ.c[0] + rb * Math.cos(t), occ.c[1] + rb * Math.sin(t), occ.cap]);
    }
    return out;
  };

  // A GPU view as vector SVG (the twin of emit/svg.py _bake_gpu_view): faces
  // painter-sorted far to near, then the visible (or, for `hid`, hidden) parts
  // of its lines in node order. For print, thumbnails, and browsers without WebGL.
  LMRW.renderGV = function (nodes, val, cam, occ, ppu, meshes) {
    var faces = [], lines = [], hasMeshes = !!(occ && occ.meshes);
    nodes.forEach(function (node) {
      var v = val(node, 'v');
      if (v && v[0] < 0.5) return;
      var dim = 1, g3 = val(node, 'g3');
      if (g3 && LMRW.occludes(occ, cam, g3[0], g3[1], g3[2])) dim = node.ga === undefined ? 0.3 : node.ga;
      var fo = val(node, 'fo'), fc = val(node, 'fc'), so = val(node, 'so'), sw = val(node, 'sw'), sc = val(node, 'sc');
      var fov = (fo ? fo[0] : 0) * dim, sov = (so ? so[0] : 0) * dim, swv = sw ? sw[0] : 0;
      if (node.wk === 'mesh') {
        var m = meshes[node.i];
        if (!m || fov <= 0.001) return;
        var edge = node.edge, ew = (edge ? edge[1] : 0.6) / ppu;
        LMRW.painterFaces(cam, m.P, m.geo, !!node.cull).forEach(function (f) {
          var col = [node.fcs[3 * f[0]] / 255, node.fcs[3 * f[0] + 1] / 255, node.fcs[3 * f[0] + 2] / 255];
          var ecol = edge ? [col[0] * (1 - edge[0]), col[1] * (1 - edge[0]), col[2] * (1 - edge[0])] : col;
          faces.push([f[1], fov < 0.999
            ? '<path d="' + path2(f[2], true) + '" fill="' + hex(col) + '" stroke="none" fill-opacity="' + fnum(fov) + '"/>'
            : '<path d="' + path2(f[2], true) + '" fill="' + hex(col) + '" stroke="' + hex(ecol) + '" stroke-width="' + fnum(ew) + '"/>']);
        });
        return;
      }
      if (node.wr === 'cull') {
        var nr = node.nrm, tw = LMRW.toward(cam);
        if (!(nr[0] * tw[0] + nr[1] * tw[1] + nr[2] * tw[2] > 0)) return;
      }
      var polys = LMRW.nodePolys(node, val, cam, occ, meshes);
      if (!polys.length) return;
      if (node.wk === 'poly' && fov > 0.001) {           // a filled 3-D polygon: a face
        polys.forEach(function (pc) {
          var P = pc[0], cx = 0, cy = 0, cz = 0;
          P.forEach(function (p) { cx += p[0]; cy += p[1]; cz += p[2]; });
          var dd = LMRW.depth(cam, cx / P.length, cy / P.length, cz / P.length);
          var stroke = sov > 0.001 && swv > 1e-4
            ? ' stroke="' + hex(sc) + '" stroke-width="' + fnum(swv / ppu) + '" stroke-linejoin="round"' + (sov < 0.999 ? ' stroke-opacity="' + fnum(sov) + '"' : '')
            : ' stroke="none"';
          faces.push([dd, '<path d="' + path2(P.map(function (p) { return LMRW.project(cam, p[0], p[1], p[2]); }), true) +
                      '" fill="' + hex(fc) + '"' + (fov < 0.999 ? ' fill-opacity="' + fnum(fov) + '"' : '') + stroke + '/>']);
        });
        return;
      }
      if (sov <= 0.001 || swv <= 1e-4) return;
      var dr = val(node, 'dr') || [0, 1];
      if (dr[1] - dr[0] < 1e-4) return;
      var rule = node.wk === 'contour' ? 'vis' : node.wr;
      var eff = (rule === 'vis' || rule === 'hid') ? rule : (hasMeshes ? 'vis' : null);
      var locc = node.wk === 'contour' ? LMRW.contourOccluder(occ) : occ;
      var attrs = 'fill="none" stroke="' + hex(sc) + '" stroke-width="' + fnum(swv / ppu) + '" stroke-linecap="round" stroke-linejoin="round"' +
        (sov < 0.999 ? ' stroke-opacity="' + fnum(sov) + '"' : '') +
        (node.dash ? ' stroke-dasharray="' + node.dash.map(fnum).join(' ') + '"' : '');
      polys.forEach(function (pc) {
        var P = pc[0], cl = pc[1];
        if (dr[0] > 1e-4 || dr[1] < 0.9999) { P = LMRW.trim3(P, cl, dr[0], dr[1]); cl = false; }
        if (!eff || !occ) {
          if (eff === 'hid') return;
          lines.push('<path d="' + path2(P.map(function (p) { return LMRW.project(cam, p[0], p[1], p[2]); }), cl) + '" ' + attrs + '/>');
          return;
        }
        var flat = [];
        P.forEach(function (p) { flat.push(p[0], p[1], p[2]); });
        LMRW.split(locc, cam, flat, 0, P.length, cl, eff === 'vis').forEach(function (idx) {
          lines.push('<path d="' + path2(idx.map(function (i) { return LMRW.project(cam, P[i][0], P[i][1], P[i][2]); }), false) + '" ' + attrs + '/>');
        });
      });
    });
    faces.sort(function (a, b) { return a[0] - b[0]; });
    return faces.map(function (f) { return f[1]; }).join('') + lines.join('');
  };

  window.LMRW = LMRW;
})();
