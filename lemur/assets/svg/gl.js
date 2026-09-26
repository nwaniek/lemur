/* WebGL renderer for GPU views (`View(renderer="gpu")` in a lemur.anim animation).
 *
 * The animation player (runtime.js) hands every frame of a GPU view to draw():
 * the view's meshes, filled 3-D polygons and lines at time t, and its camera.
 * They are drawn on a canvas that sits in the animation's layer order (the SVG
 * shapes before it are below, labels and 2-D shapes after it are on top), with
 * a depth buffer, so anything hides anything:
 *   - opaque faces first (backface-culled where asked), their fine mesh lines
 *     just in front;
 *   - translucent faces sorted far to near;
 *   - lines as anti-aliased capsules (round joins and caps), dashed and drawn
 *     on by arc length, each node once per pixel (a stencil); a `hid` line is
 *     drawn only where it is behind something, every other line where it is not
 *     (a small bias keeps curves drawn *on* a surface in front of it).
 * The same geometry as a vector still — for print, thumbnails, and browsers
 * without WebGL 2 — comes from LMRW.renderGV (svg/world.js), the twin of the
 * build-time still. Only the slide on screen holds a WebGL context. */
(function () {
  var PLUGINS = window.LMR_PLUGINS = window.LMR_PLUGINS || [];
  var slides = [].slice.call(document.querySelectorAll('.slide'));
  var renderers = [];
  var MESH_EPS = 2e-2, CONTOUR_EPS_SCALE = 4.0;

  var FACE_VS = '#version 300 es\n' +
    'in vec3 aPos; in vec3 aCol; uniform mat4 uM; uniform float uAlpha; out vec4 vCol;\n' +
    'void main() { gl_Position = uM * vec4(aPos, 1.0); vCol = vec4(aCol * uAlpha, uAlpha); }\n';
  var FACE_FS = '#version 300 es\nprecision highp float;\n' +
    'in vec4 vCol; out vec4 o; void main() { o = vCol; }\n';
  var LINE_VS = '#version 300 es\n' +
    'in vec2 aCorner; in vec3 aP0; in vec3 aP1; in vec4 aArc;\n' +
    'uniform mat4 uM; uniform vec2 uHalf; uniform float uR; uniform float uBias;\n' +
    'out vec2 vLocal; flat out float vLen; flat out vec4 vArc;\n' +
    'void main() {\n' +
    '  vec4 c0 = uM * vec4(aP0, 1.0), c1 = uM * vec4(aP1, 1.0);\n' +
    '  vec2 s0 = c0.xy / c0.w * uHalf, s1 = c1.xy / c1.w * uHalf;\n' +
    '  vec2 d = s1 - s0; float len = length(d);\n' +
    '  vec2 dir = len > 1e-6 ? d / len : vec2(1.0, 0.0); vec2 nrm = vec2(-dir.y, dir.x);\n' +
    '  vec2 pos = mix(s0, s1, aCorner.x) + dir * (aCorner.x * 2.0 - 1.0) * uR + nrm * aCorner.y * uR;\n' +
    '  vLocal = vec2(dot(pos - s0, dir), dot(pos - s0, nrm)); vLen = len; vArc = aArc;\n' +
    '  float z = mix(c0.z / c0.w, c1.z / c1.w, aCorner.x);\n' +
    '  gl_Position = vec4(pos / uHalf, z - uBias, 1.0);\n' +
    '}\n';
  var LINE_FS = '#version 300 es\nprecision highp float;\n' +
    'in vec2 vLocal; flat in float vLen; flat in vec4 vArc;\n' +
    'uniform vec4 uCol; uniform float uW; uniform vec2 uRange; uniform vec2 uDash; uniform float uDashScale;\n' +
    'uniform float uPass;\n' +
    'out vec4 o;\n' +
    'void main() {\n' +
    '  float x = clamp(vLocal.x, 0.0, vLen);\n' +
    '  float a = clamp(uW + 0.5 - length(vLocal - vec2(x, 0.0)), 0.0, 1.0);\n' +
    '  if (a <= 0.0 || (uPass < 0.5 ? a < 0.999 : a >= 0.999)) discard;\n' +
    '  float u = vLen > 1e-6 ? x / vLen : 0.0;\n' +
    '  float frac = mix(vArc.z, vArc.w, u);\n' +
    '  if (frac < uRange.x || frac > uRange.y) discard;\n' +
    '  if (uDash.x > 0.0) { float m = mod(mix(vArc.x, vArc.y, u) * uDashScale, uDash.x + uDash.y); if (m > uDash.x) discard; }\n' +
    '  o = uCol * a;\n' +
    '}\n';

  function compile(gl, vs, fs) {
    var p = gl.createProgram();
    [[gl.VERTEX_SHADER, vs], [gl.FRAGMENT_SHADER, fs]].forEach(function (s) {
      var sh = gl.createShader(s[0]);
      gl.shaderSource(sh, s[1]);
      gl.compileShader(sh);
      if (!gl.getShaderParameter(sh, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(sh));
      gl.attachShader(p, sh);
    });
    gl.linkProgram(p);
    if (!gl.getProgramParameter(p, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(p));
    var u = {}, n = gl.getProgramParameter(p, gl.ACTIVE_UNIFORMS);
    for (var i = 0; i < n; i++) { var nm = gl.getActiveUniform(p, i).name; u[nm] = gl.getUniformLocation(p, nm); }
    return { prog: p, u: u };
  }

  // the clip-space matrix of a view (column-major): world → the canvas, with a
  // depth range [dmid ± dhalf] (nearer = smaller z); perspective via w
  function viewMatrix(c, camMat, vp, dmid, dhalf) {
    var ca = Math.cos(c.a), sa = Math.sin(c.a), se = Math.sin(c.e), ce = Math.cos(c.e), o = c.o;
    var row = function (r) { return [r[0], r[1], r[2], -(r[0] * o[0] + r[1] * o[1] + r[2] * o[2])]; };
    var SX = row([ca, -sa, 0]), SY = row([sa * se, ca * se, ce]), DC = row([-sa * ce, -ca * ce, se]);
    var W = (c.p !== null && c.p !== undefined)
      ? [-DC[0] / c.p, -DC[1] / c.p, -DC[2] / c.p, 1 - DC[3] / c.p] : [0, 0, 0, 1];
    var s = camMat[0], ox = camMat[1], oy = camMat[2];
    var ax = 2 * s / vp[2], bx = (ox - vp[0]) * 2 / vp[2] - 1;
    var ay = 2 * s / vp[3], by = 1 - (oy - vp[1]) * 2 / vp[3];
    var X = [], Y = [], Z = [], i;
    for (i = 0; i < 4; i++) {
      X.push(ax * c.s * SX[i] + (ax * c.c[0] + bx) * W[i]);
      Y.push(ay * c.s * SY[i] + (ay * c.c[1] + by) * W[i]);
      Z.push(((i === 3 ? dmid : 0) - DC[i]) / dhalf);
    }
    return new Float32Array([X[0], Y[0], Z[0], W[0], X[1], Y[1], Z[1], W[1],
                             X[2], Y[2], Z[2], W[2], X[3], Y[3], Z[3], W[3]]);
  }

  function Renderer(player) {
    this.p = player;
    this.box = player.root.querySelector('.lmr-gl-box');
    var sl = player.root.closest('.slide');
    this.slide = slides.indexOf(sl);
    this.gl = null; this.failed = false; this.mesh = {};
  }

  Renderer.prototype.start = function () {
    if (this.gl || this.failed || !this.box) return;
    var c = document.createElement('canvas');
    this.box.appendChild(c);
    var gl = c.getContext('webgl2', { antialias: true, alpha: true, premultipliedAlpha: true,
                                      stencil: true, depth: true });
    if (!gl) { this.failed = true; c.remove(); return; }
    try {
      this.faceP = compile(gl, FACE_VS, FACE_FS);
      this.lineP = compile(gl, LINE_VS, LINE_FS);
    } catch (e) {
      if (window.console) console.warn('lemur GPU view: ' + e.message);
      this.failed = true; c.remove(); return;
    }
    this.corner = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, this.corner);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([0, -1, 0, 1, 1, -1, 1, 1]), gl.STATIC_DRAW);
    this.inst = gl.createBuffer();
    this.dyn = gl.createBuffer(); this.dynCol = gl.createBuffer();
    this.canvas = c; this.gl = gl; this.mesh = {};
  };

  Renderer.prototype.stop = function () {
    if (!this.gl) return;
    var ext = this.gl.getExtension('WEBGL_lose_context');
    if (ext) ext.loseContext();
    this.canvas.remove();
    this.gl = null; this.mesh = {};
  };

  Renderer.prototype.draw = function (t, cams, mo) {
    if (!this.gl) return false;
    try { this.frame(t, cams, mo); return true; }
    catch (e) {
      if (window.console) console.warn('lemur GPU view: ' + (e && e.message));
      this.stop(); this.failed = true; return false;
    }
  };

  // a mesh node's GPU buffers: every triangle expanded with its face colour, and
  // the face outlines as lines (rebuilt when the vertices change)
  Renderer.prototype.meshBufs = function (nd, P, geo) {
    var gl = this.gl, m = this.mesh[nd.i];
    if (m && m.P === P) return m;
    var k = geo.k, F = geo.faces.length / k, tris = geo.tris, per = k - 2;
    if (!m) {
      m = this.mesh[nd.i] = { pos: gl.createBuffer(), col: gl.createBuffer(), epos: gl.createBuffer(), ecol: gl.createBuffer() };
      var col = new Float32Array(tris.length * 3), i, j;
      for (i = 0; i < tris.length / 3; i++) {
        var f = Math.floor(i / per);
        for (j = 0; j < 3; j++) {
          col[9 * i + 3 * j] = nd.fcs[3 * f] / 255; col[9 * i + 3 * j + 1] = nd.fcs[3 * f + 1] / 255;
          col[9 * i + 3 * j + 2] = nd.fcs[3 * f + 2] / 255;
        }
      }
      gl.bindBuffer(gl.ARRAY_BUFFER, m.col); gl.bufferData(gl.ARRAY_BUFFER, col, gl.STATIC_DRAW);
      if (nd.edge) {
        var ec = new Float32Array(F * k * 2 * 3), dk = 1 - nd.edge[0];
        for (i = 0; i < F; i++) for (j = 0; j < 2 * k; j++) {
          var q = 3 * (i * 2 * k + j);
          ec[q] = nd.fcs[3 * i] / 255 * dk; ec[q + 1] = nd.fcs[3 * i + 1] / 255 * dk; ec[q + 2] = nd.fcs[3 * i + 2] / 255 * dk;
        }
        gl.bindBuffer(gl.ARRAY_BUFFER, m.ecol); gl.bufferData(gl.ARRAY_BUFFER, ec, gl.STATIC_DRAW);
      }
      m.n = tris.length; m.en = F * k * 2;
    }
    var pos = new Float32Array(tris.length * 3);
    for (var a = 0; a < tris.length; a++) {
      pos[3 * a] = P[3 * tris[a]]; pos[3 * a + 1] = P[3 * tris[a] + 1]; pos[3 * a + 2] = P[3 * tris[a] + 2];
    }
    gl.bindBuffer(gl.ARRAY_BUFFER, m.pos); gl.bufferData(gl.ARRAY_BUFFER, pos, gl.DYNAMIC_DRAW);
    if (nd.edge) {
      var ep = new Float32Array(m.en * 3), w = 0, f2 = geo.faces;
      for (var b = 0; b < F; b++) for (var e = 0; e < k; e++) {
        var v0 = f2[b * k + e], v1 = f2[b * k + (e + 1) % k];
        ep[w++] = P[3 * v0]; ep[w++] = P[3 * v0 + 1]; ep[w++] = P[3 * v0 + 2];
        ep[w++] = P[3 * v1]; ep[w++] = P[3 * v1 + 1]; ep[w++] = P[3 * v1 + 2];
      }
      gl.bindBuffer(gl.ARRAY_BUFFER, m.epos); gl.bufferData(gl.ARRAY_BUFFER, ep, gl.DYNAMIC_DRAW);
    }
    m.P = P;
    return m;
  };

  Renderer.prototype.bindFace = function (pos, col) {
    var gl = this.gl, F = this.faceP;
    var lp = gl.getAttribLocation(F.prog, 'aPos'), lc = gl.getAttribLocation(F.prog, 'aCol');
    gl.bindBuffer(gl.ARRAY_BUFFER, pos); gl.enableVertexAttribArray(lp); gl.vertexAttribPointer(lp, 3, gl.FLOAT, false, 0, 0);
    gl.bindBuffer(gl.ARRAY_BUFFER, col); gl.enableVertexAttribArray(lc); gl.vertexAttribPointer(lc, 3, gl.FLOAT, false, 0, 0);
  };

  Renderer.prototype.frame = function (t, cams, mo) {
    var gl = this.gl, c = this.canvas, p = this.p, LMRW = window.LMRW, self = this;
    var r = c.getBoundingClientRect();
    if (r.width < 2 || r.height < 2) return;
    var dpr = Math.min(window.devicePixelRatio || 1, 2);
    var W = Math.max(1, Math.round(r.width * dpr)), H = Math.max(1, Math.round(r.height * dpr));
    if (c.width !== W || c.height !== H) { c.width = W; c.height = H; }
    gl.viewport(0, 0, W, H);
    gl.clearColor(0, 0, 0, 0); gl.clearDepth(1); gl.clearStencil(0);
    gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT | gl.STENCIL_BUFFER_BIT);
    gl.enable(gl.DEPTH_TEST); gl.enable(gl.BLEND); gl.blendFunc(gl.ONE, gl.ONE_MINUS_SRC_ALPHA);
    var pxPerSlide = W / p.vp[2], val = function (nd, prop) { return p.val(nd, prop, t); };

    var byView = {};
    p.gnodes.forEach(function (nd) { (byView[nd.w] = byView[nd.w] || []).push(nd); });
    for (var k in byView) {
      var cam = cams[k], occ = mo.occ[k] || p.views[k].occ, nodes = byView[k];
      // what each node draws at t
      var items = nodes.map(function (nd) {
        var v = val(nd, 'v');
        if (v && v[0] < 0.5) return null;
        if (nd.wr === 'cull') {
          var nr = nd.nrm, tw = LMRW.toward(cam);
          if (!(nr[0] * tw[0] + nr[1] * tw[1] + nr[2] * tw[2] > 0)) return null;
        }
        var dim = 1, g3 = val(nd, 'g3');
        if (g3 && LMRW.occludes(occ, cam, g3[0], g3[1], g3[2])) dim = nd.ga === undefined ? 0.3 : nd.ga;
        var fo = val(nd, 'fo'), so = val(nd, 'so');
        var it = { nd: nd, fo: (fo ? fo[0] : 0) * dim, so: (so ? so[0] : 0) * dim, fc: val(nd, 'fc'), sc: val(nd, 'sc'),
                   sw: (val(nd, 'sw') || [0])[0], dr: val(nd, 'dr') || [0, 1] };
        if (nd.wk === 'mesh') it.m = mo.meshes[nd.i];
        else it.polys = LMRW.nodePolys(nd, val, cam, occ, mo.meshes);
        return it;
      }).filter(Boolean);
      // the depth range of everything drawn
      var dmin = Infinity, dmax = -Infinity, size = 0;
      var see = function (x, y, z) { var d = LMRW.depth(cam, x, y, z); if (d < dmin) dmin = d; if (d > dmax) dmax = d; };
      items.forEach(function (it) {
        if (it.m) for (var i = 0; i < it.m.P.length; i += 3) see(it.m.P[i], it.m.P[i + 1], it.m.P[i + 2]);
        (it.polys || []).forEach(function (pc) { pc[0].forEach(function (q) { see(q[0], q[1], q[2]); }); });
        if (it.m && it.m.occ) size = Math.max(size, it.m.occ.eps / MESH_EPS);
      });
      if (!isFinite(dmin)) continue;
      var dmid = (dmin + dmax) / 2, dhalf = Math.max((dmax - dmin) / 2, 1e-3) * 1.2;
      if (cam.p !== null && cam.p !== undefined) {
        var wlo = 1 - dmin / cam.p, whi = 1 - dmax / cam.p;
        dhalf = Math.max(Math.abs(dmid - dmin) / Math.max(wlo, 1e-3), Math.abs(dmid - dmax) / Math.max(whi, 1e-3)) * 1.2;
      }
      var M = viewMatrix(cam, p.camMat, p.vp, dmid, dhalf);
      var bias = (size || Math.max(dmax - dmin, 1e-3) / 2) * MESH_EPS / dhalf;

      // opaque faces: meshes, then filled polygons
      gl.useProgram(this.faceP.prog);
      gl.uniformMatrix4fv(this.faceP.u.uM, false, M);
      gl.depthMask(true); gl.depthFunc(gl.LESS);
      gl.enable(gl.POLYGON_OFFSET_FILL); gl.polygonOffset(1, 1);
      var clear = [];
      items.forEach(function (it) {
        if (it.m && it.fo > 0.001) {
          var bufs = self.meshBufs(it.nd, it.m.P, it.m.geo);
          if (it.fo < 0.999) { clear.push(it); return; }
          if (it.nd.cull) { gl.enable(gl.CULL_FACE); gl.cullFace(gl.BACK); gl.frontFace(gl.CCW); } else gl.disable(gl.CULL_FACE);
          gl.uniform1f(self.faceP.u.uAlpha, 1);
          self.bindFace(bufs.pos, bufs.col);
          gl.drawArrays(gl.TRIANGLES, 0, bufs.n);
        } else if (it.polys && it.nd.wk === 'poly' && it.fo > 0.001) {
          if (it.fo < 0.999) { clear.push(it); return; }
          gl.disable(gl.CULL_FACE);
          self.fillPolys(it.polys, it.fc, 1);
        }
      });
      gl.disable(gl.CULL_FACE);
      gl.disable(gl.POLYGON_OFFSET_FILL);
      // the fine mesh lines, just in front of their faces
      gl.depthFunc(gl.LEQUAL);
      items.forEach(function (it) {
        if (!it.m || !it.nd.edge || it.fo <= 0.001) return;
        var bufs = self.mesh[it.nd.i];
        gl.uniform1f(self.faceP.u.uAlpha, it.fo);
        self.bindFace(bufs.epos, bufs.ecol);
        gl.drawArrays(gl.LINES, 0, bufs.en);
      });
      // translucent faces, far to near, not writing depth
      if (clear.length) {
        gl.depthMask(false);
        clear.forEach(function (it) {
          if (it.m) {
            var bufs = self.meshBufs(it.nd, it.m.P, it.m.geo);
            if (it.nd.cull) { gl.enable(gl.CULL_FACE); gl.cullFace(gl.BACK); } else gl.disable(gl.CULL_FACE);
            gl.uniform1f(self.faceP.u.uAlpha, it.fo);
            self.bindFace(bufs.pos, bufs.col);
            gl.drawArrays(gl.TRIANGLES, 0, bufs.n);
          } else {
            gl.disable(gl.CULL_FACE);
            self.fillPolys(it.polys, it.fc, it.fo);
          }
        });
        gl.disable(gl.CULL_FACE);
        gl.depthMask(true);
      }
      // lines, in node order
      gl.useProgram(this.lineP.prog);
      gl.uniformMatrix4fv(this.lineP.u.uM, false, M);
      gl.uniform2f(this.lineP.u.uHalf, W / 2, H / 2);
      gl.depthMask(false);
      gl.enable(gl.STENCIL_TEST);
      items.forEach(function (it) {
        if (!it.polys || !it.polys.length || it.so <= 0.001 || it.sw <= 1e-4) return;
        if (it.nd.wk === 'poly' && it.fo > 0.001 && !(it.so > 0.001)) return;
        if (it.dr[1] - it.dr[0] < 1e-4) return;
        var rule = it.nd.wk === 'contour' ? 'vis' : it.nd.wr;
        gl.depthFunc(rule === 'hid' ? gl.GREATER : gl.LEQUAL);
        var b = it.nd.wk === 'contour' ? bias * CONTOUR_EPS_SCALE : bias;
        var wpx = it.sw / p.ppu * p.camMat[0] * pxPerSlide;
        var sc = it.sc || [1, 1, 1];
        gl.uniform4f(self.lineP.u.uCol, sc[0] * it.so, sc[1] * it.so, sc[2] * it.so, it.so);
        gl.uniform1f(self.lineP.u.uW, wpx / 2);
        gl.uniform1f(self.lineP.u.uR, wpx / 2 + 1);
        gl.uniform1f(self.lineP.u.uBias, b);                 // toward the camera: on-surface curves count as in front
        gl.uniform2f(self.lineP.u.uRange, it.dr[0] - 1e-6, it.dr[1] + 1e-6);
        var dash = it.nd.dash;
        gl.uniform2f(self.lineP.u.uDash, dash ? dash[0] : 0, dash ? dash[1] : 0);
        gl.uniform1f(self.lineP.u.uDashScale, cam.s);
        // each pixel once: the solid cores first, then the anti-aliased fringes
        // where no core landed (so neither joins nor fringes double up)
        gl.clear(gl.STENCIL_BUFFER_BIT);
        gl.stencilFunc(gl.EQUAL, 0, 0xff); gl.stencilOp(gl.KEEP, gl.KEEP, gl.INCR);
        gl.uniform1f(self.lineP.u.uPass, 0);
        self.strokePolys(it.polys);
        gl.uniform1f(self.lineP.u.uPass, 1);
        self.strokePolys(it.polys, true);
      });
      gl.disable(gl.STENCIL_TEST);
      gl.depthMask(true);
    }
  };

  // filled 3-D polygons (fan triangles) in one colour
  Renderer.prototype.fillPolys = function (polys, fc, alpha) {
    var gl = this.gl, pos = [], col = [], rgb = fc || [1, 1, 1];
    polys.forEach(function (pc) {
      var P = pc[0];
      for (var i = 1; i + 1 < P.length; i++) [P[0], P[i], P[i + 1]].forEach(function (q) {
        pos.push(q[0], q[1], q[2]); col.push(rgb[0], rgb[1], rgb[2]);
      });
    });
    if (!pos.length) return;
    gl.bindBuffer(gl.ARRAY_BUFFER, this.dyn); gl.bufferData(gl.ARRAY_BUFFER, new Float32Array(pos), gl.STREAM_DRAW);
    gl.bindBuffer(gl.ARRAY_BUFFER, this.dynCol); gl.bufferData(gl.ARRAY_BUFFER, new Float32Array(col), gl.STREAM_DRAW);
    gl.uniform1f(this.faceP.u.uAlpha, alpha);
    this.bindFace(this.dyn, this.dynCol);
    gl.drawArrays(gl.TRIANGLES, 0, pos.length / 3);
  };

  // polylines as instanced capsules: per segment its ends, arc lengths and fractions
  Renderer.prototype.strokePolys = function (polys, again) {
    var gl = this.gl, L = this.lineP.prog, data = [];
    if (again && this.lastInst) { this.drawInst(this.lastInst); return; }
    polys.forEach(function (pc) {
      var P = pc[1] ? pc[0].concat([pc[0][0]]) : pc[0], cum = [0], i;
      for (i = 1; i < P.length; i++) cum.push(cum[i - 1] + Math.hypot(P[i][0] - P[i - 1][0], P[i][1] - P[i - 1][1], P[i][2] - P[i - 1][2]));
      var tot = cum[cum.length - 1] || 1;
      for (i = 1; i < P.length; i++) {
        var a = P[i - 1], b = P[i];
        data.push(a[0], a[1], a[2], b[0], b[1], b[2], cum[i - 1], cum[i], cum[i - 1] / tot, cum[i] / tot);
      }
    });
    this.lastInst = data.length / 10;
    if (!data.length) return;
    gl.bindBuffer(gl.ARRAY_BUFFER, this.inst);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array(data), gl.STREAM_DRAW);
    this.drawInst(this.lastInst);
  };

  Renderer.prototype.drawInst = function (n) {
    var gl = this.gl, L = this.lineP.prog;
    var lc = gl.getAttribLocation(L, 'aCorner'), l0 = gl.getAttribLocation(L, 'aP0'),
        l1 = gl.getAttribLocation(L, 'aP1'), la = gl.getAttribLocation(L, 'aArc');
    gl.bindBuffer(gl.ARRAY_BUFFER, this.corner);
    gl.enableVertexAttribArray(lc); gl.vertexAttribPointer(lc, 2, gl.FLOAT, false, 0, 0); gl.vertexAttribDivisor(lc, 0);
    gl.bindBuffer(gl.ARRAY_BUFFER, this.inst);
    gl.enableVertexAttribArray(l0); gl.vertexAttribPointer(l0, 3, gl.FLOAT, false, 40, 0); gl.vertexAttribDivisor(l0, 1);
    gl.enableVertexAttribArray(l1); gl.vertexAttribPointer(l1, 3, gl.FLOAT, false, 40, 12); gl.vertexAttribDivisor(l1, 1);
    gl.enableVertexAttribArray(la); gl.vertexAttribPointer(la, 4, gl.FLOAT, false, 40, 24); gl.vertexAttribDivisor(la, 1);
    gl.drawArraysInstanced(gl.TRIANGLE_STRIP, 0, 4, n);
    [l0, l1, la].forEach(function (x) { gl.vertexAttribDivisor(x, 0); gl.disableVertexAttribArray(x); });
  };

  window.LMRGL = {
    attach: function (player) { var r = new Renderer(player); renderers.push(r); return r; }
  };

  PLUGINS.push({
    // only the slide on screen holds a WebGL context; a slide being left keeps a
    // vector still of its current frame (for the transition and the overview)
    show: function (i) {
      renderers.forEach(function (r) {
        if (r.slide === i) {
          if (!r.gl && !r.failed) { r.start(); if (r.gl) r.p.apply(r.p.t); }
        } else if (r.gl) {
          r.stop();
          r.p.apply(r.p.t);
        }
      });
    },
    thumb: function (svg) {
      [].slice.call(svg.querySelectorAll('.lmr-gv')).forEach(function (g) { g.style.display = ''; });
      [].slice.call(svg.querySelectorAll('.lmr-gl-box')).forEach(function (b) { b.innerHTML = ''; });
    }
  });
})();
