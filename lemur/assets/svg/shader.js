/* Live GPU shaders for lemur SVG decks (`!shader` blocks) — a plugin of the
 * display runtime (registered in window.LMR_PLUGINS before runtime.js runs).
 *
 * Each `<foreignObject class="lmr-shader" data-glsl=…>` holds a GLSL fragment
 * shader in Shadertoy's convention, `void mainImage(out vec4 c, in vec2 p)`,
 * with the uniforms iResolution, iTime, iTimeDelta, iFrame, iMouse — plus
 * lemur's own: iStep (the slide step past the reveals, *eased*, so a keypress
 * glides the scene to its next state), iStepRaw (the same, as an int) and
 * iSteps (how many steps the block declared).
 *
 * WebGL contexts are scarce (browsers keep ~16), so a context exists only for
 * the slide on screen: on leaving, the last frame is kept as a poster <img>
 * (thumbnails and print show it) and the context is released. Resolution
 * adapts to hold the frame rate. A shader that fails to compile shows its
 * log, with line numbers of the author's file. `!sound <preset>` adds an
 * optional generative soundtrack — off until the presenter presses 'm'. */
(function () {
  var PLUGINS = window.LMR_PLUGINS = window.LMR_PLUGINS || [];
  var slides = [].slice.call(document.querySelectorAll('.slide'));
  var HEAD = '#version 300 es\nprecision highp float;\nprecision highp int;\n' +
    'uniform vec3 iResolution;\nuniform float iTime;\nuniform float iTimeDelta;\n' +
    'uniform int iFrame;\nuniform vec4 iMouse;\nuniform float iStep;\nuniform int iStepRaw;\n' +
    'uniform float iSteps;\nout vec4 lmr_FragColor;\n';
  var HEAD_LINES = HEAD.split('\n').length - 1;
  var TAIL = '\nvoid main() { vec4 c = vec4(0.0, 0.0, 0.0, 1.0); mainImage(c, gl_FragCoord.xy);' +
    ' lmr_FragColor = vec4(c.rgb, 1.0); }\n';
  var VERT = '#version 300 es\nin vec2 p;\nvoid main() { gl_Position = vec4(p, 0.0, 1.0); }\n';

  function decode(b64) {
    var bin = atob(b64), bytes = new Uint8Array(bin.length);
    for (var i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
    return new TextDecoder('utf-8').decode(bytes);
  }

  function Shader(fo) {
    this.fo = fo;
    this.box = fo.querySelector('.lmr-shader-box');
    this.src = decode(fo.getAttribute('data-glsl'));
    this.nsteps = +(fo.getAttribute('data-shader-steps') || 0);
    this.sound = fo.getAttribute('data-sound');
    var q = parseFloat(fo.getAttribute('data-quality') || '1');
    this.maxScale = isFinite(q) && q > 0 ? Math.min(q, 2) : 1;
    this.scale = this.maxScale;
    this.time = 0; this.frame = 0;
    this.stepTarget = 0; this.stepNow = 0;
    this.gl = null; this.canvas = null; this.poster = null;
    this.slow = 0; this.fast = 0;
    this.mouse = [0, 0, 0, 0];
  }

  Shader.prototype.start = function () {
    if (this.gl) return true;
    var c = document.createElement('canvas');
    c.className = 'lmr-shader-canvas';
    var gl = c.getContext('webgl2', { preserveDrawingBuffer: true, antialias: false, alpha: false,
                                      premultipliedAlpha: false, powerPreference: 'high-performance' });
    if (!gl) { this.fail('WebGL 2 is not available in this browser.'); return false; }
    var prog = link(gl, VERT, HEAD + this.src + TAIL);
    if (prog.error) { this.fail(prog.error); return false; }
    this.box.innerHTML = '';
    if (this.poster) this.box.appendChild(this.poster);   // shown until the first frame lands
    this.box.appendChild(c);
    this.canvas = c; this.gl = gl; this.prog = prog;
    var buf = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, buf);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW);
    var loc = gl.getAttribLocation(prog, 'p');
    gl.enableVertexAttribArray(loc);
    gl.vertexAttribPointer(loc, 2, gl.FLOAT, false, 0, 0);
    gl.useProgram(prog);
    var u = {};
    ['iResolution', 'iTime', 'iTimeDelta', 'iFrame', 'iMouse', 'iStep', 'iStepRaw', 'iSteps']
      .forEach(function (n) { u[n] = gl.getUniformLocation(prog, n); });
    this.u = u;
    var self = this;
    c.addEventListener('pointermove', function (ev) {
      var r = c.getBoundingClientRect();
      self.mouse[0] = (ev.clientX - r.left) / r.width * c.width;
      self.mouse[1] = (1 - (ev.clientY - r.top) / r.height) * c.height;
    });
    return true;
  };

  Shader.prototype.fail = function (msg) {
    this.box.innerHTML = '';
    var pre = document.createElement('pre');
    pre.className = 'lmr-shader-error';
    pre.textContent = msg;
    this.box.appendChild(pre);
    this.failed = true;
  };

  Shader.prototype.draw = function (dt) {
    var gl = this.gl, c = this.canvas;
    if (!gl) return;
    var r = c.getBoundingClientRect();
    if (r.width < 2 || r.height < 2) return;
    var dpr = Math.min(window.devicePixelRatio || 1, 2);
    var w = Math.max(1, Math.round(r.width * dpr * this.scale));
    var h = Math.max(1, Math.round(r.height * dpr * this.scale));
    if (c.width !== w || c.height !== h) { c.width = w; c.height = h; }
    gl.viewport(0, 0, w, h);
    // ease the step toward its target (~0.6 s time constant)
    this.stepNow += (this.stepTarget - this.stepNow) * (1 - Math.exp(-dt / 0.6));
    if (Math.abs(this.stepTarget - this.stepNow) < 1e-4) this.stepNow = this.stepTarget;
    this.time += dt;
    var u = this.u;
    gl.uniform3f(u.iResolution, w, h, 1);
    gl.uniform1f(u.iTime, this.time);
    gl.uniform1f(u.iTimeDelta, dt);
    gl.uniform1i(u.iFrame, this.frame++);
    gl.uniform4f(u.iMouse, this.mouse[0], this.mouse[1], this.mouse[2], this.mouse[3]);
    gl.uniform1f(u.iStep, this.stepNow);
    gl.uniform1i(u.iStepRaw, this.stepTarget);
    gl.uniform1f(u.iSteps, this.nsteps);
    gl.drawArrays(gl.TRIANGLES, 0, 3);
    if (this.poster && this.frame > 2) { this.poster.remove(); this.poster = null; }
  };

  // keep the frame rate: frame times above ~26 ms lower the resolution, below
  // ~13 ms raise it again (never above the author's `!quality`)
  Shader.prototype.adapt = function (ms) {
    if (ms > 26) { this.slow++; this.fast = 0; } else if (ms < 13) { this.fast++; this.slow = 0; }
    else { this.slow = this.fast = 0; }
    if (this.slow > 8) { this.scale = Math.max(0.3, this.scale * 0.8); this.slow = 0; }
    if (this.fast > 90) { this.scale = Math.min(this.maxScale, this.scale * 1.15); this.fast = 0; }
  };

  Shader.prototype.stop = function () {
    if (!this.gl) return;
    try {
      var img = document.createElement('img');
      img.className = 'lmr-shader-poster';
      img.src = this.canvas.toDataURL('image/jpeg', 0.85);
      this.poster = img;
    } catch (e) { this.poster = null; }
    var ext = this.gl.getExtension('WEBGL_lose_context');
    if (ext) ext.loseContext();
    this.gl = null;
    this.box.innerHTML = '';
    if (this.poster) this.box.appendChild(this.poster);
  };

  function compile(gl, type, src) {
    var s = gl.createShader(type);
    gl.shaderSource(s, src);
    gl.compileShader(s);
    if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) {
      var log = gl.getShaderInfoLog(s) || 'compile error';
      // report line numbers of the author's file, not of the wrapped source
      log = log.replace(/(ERROR: \d+:)(\d+)/g, function (_, a, n) { return a + (+n - HEAD_LINES); });
      return { error: 'GLSL error (lines are those of the !shader file):\n' + log };
    }
    return { shader: s };
  }

  function link(gl, vs, fs) {
    var v = compile(gl, gl.VERTEX_SHADER, vs);
    if (v.error) return v;
    var f = compile(gl, gl.FRAGMENT_SHADER, fs);
    if (f.error) return f;
    var p = gl.createProgram();
    gl.attachShader(p, v.shader);
    gl.attachShader(p, f.shader);
    gl.linkProgram(p);
    if (!gl.getProgramParameter(p, gl.LINK_STATUS)) return { error: gl.getProgramInfoLog(p) || 'link error' };
    return p;
  }

  var bySlide = slides.map(function (s) {
    return [].slice.call(s.querySelectorAll('foreignObject.lmr-shader')).map(function (fo) { return new Shader(fo); });
  });
  var active = -1, raf = 0, last = 0;

  function loop(now) {
    raf = requestAnimationFrame(loop);
    var dt = last ? Math.min((now - last) / 1000, 0.1) : 1 / 60;
    var t0 = performance.now();
    (bySlide[active] || []).forEach(function (sh) { sh.draw(dt); });
    var ms = now - last;
    last = now;
    if (ms > 0) (bySlide[active] || []).forEach(function (sh) { sh.adapt(ms); });
    void t0;
  }

  function show(i, localStep, jump) {
    if (i !== active) {
      (bySlide[active] || []).forEach(function (sh) { sh.stop(); });
      active = i;
      (bySlide[i] || []).forEach(function (sh) { if (!sh.failed) sh.start(); });
      if (!raf && (bySlide[i] || []).length) { last = 0; raf = requestAnimationFrame(loop); }
      if (raf && !(bySlide[i] || []).length) { cancelAnimationFrame(raf); raf = 0; }
    }
    (bySlide[i] || []).forEach(function (sh) {
      sh.stepTarget = Math.min(localStep, sh.nsteps);
      if (jump) sh.stepNow = sh.stepTarget;
    });
    Sound.follow(i, localStep);
  }

  /* ---- generative soundtrack (WebAudio), opt-in with 'm' ------------------ */
  var Sound = (function () {
    var ctx = null, master = null, on = false, voices = [], wind = null, preset = null, chordAt = -1;
    // chord progressions per preset (semitones above the root), one per step
    var PRESETS = {
      drone: { root: 45, chords: [[0, 7, 12, 16, 19], [-2, 5, 10, 14, 19], [-4, 3, 10, 15, 19], [-5, 2, 7, 14, 17]], wind: 0.05 },
      aurora: { root: 50, chords: [[0, 7, 14, 16, 23], [-3, 4, 11, 16, 19], [-7, 0, 7, 12, 16], [-5, 2, 9, 14, 21]], wind: 0.03 }
    };
    function hz(midi) { return 440 * Math.pow(2, (midi - 69) / 12); }
    function init() {
      if (ctx) return;
      ctx = new (window.AudioContext || window.webkitAudioContext)();
      master = ctx.createGain(); master.gain.value = 0;
      var comp = ctx.createDynamicsCompressor();
      // a soft generated reverb
      var rev = ctx.createConvolver(), len = ctx.sampleRate * 3.2, ir = ctx.createBuffer(2, len, ctx.sampleRate);
      for (var ch = 0; ch < 2; ch++) {
        var d = ir.getChannelData(ch);
        for (var i = 0; i < len; i++) d[i] = (Math.random() * 2 - 1) * Math.pow(1 - i / len, 2.6);
      }
      rev.buffer = ir;
      var wet = ctx.createGain(); wet.gain.value = 0.55;
      master.connect(comp); master.connect(rev); rev.connect(wet); wet.connect(comp);
      comp.connect(ctx.destination);
      for (var v = 0; v < 5; v++) {
        var g = ctx.createGain(); g.gain.value = 0;
        var f = ctx.createBiquadFilter(); f.type = 'lowpass'; f.frequency.value = 900; f.Q.value = 0.7;
        var oscs = [-6, 6].map(function (cents) {
          var o = ctx.createOscillator(); o.type = v === 0 ? 'triangle' : 'sawtooth'; o.detune.value = cents;
          o.connect(f); o.start(); return o;
        });
        var lfo = ctx.createOscillator(), lg = ctx.createGain();
        lfo.frequency.value = 0.05 + 0.03 * v; lg.gain.value = 350; lfo.connect(lg); lg.connect(f.frequency); lfo.start();
        f.connect(g); g.connect(master);
        voices.push({ oscs: oscs, gain: g });
      }
      // wind: filtered noise, swept slowly
      var nb = ctx.createBuffer(1, ctx.sampleRate * 2, ctx.sampleRate), nd = nb.getChannelData(0);
      for (var k = 0; k < nd.length; k++) nd[k] = Math.random() * 2 - 1;
      var ns = ctx.createBufferSource(); ns.buffer = nb; ns.loop = true;
      var bp = ctx.createBiquadFilter(); bp.type = 'bandpass'; bp.frequency.value = 600; bp.Q.value = 0.8;
      var sw = ctx.createOscillator(), sg = ctx.createGain(); sw.frequency.value = 0.07; sg.gain.value = 400;
      sw.connect(sg); sg.connect(bp.frequency); sw.start();
      wind = ctx.createGain(); wind.gain.value = 0;
      ns.connect(bp); bp.connect(wind); wind.connect(master); ns.start();
    }
    function chord(n) {
      if (!ctx || !preset) return;
      var P = PRESETS[preset] || PRESETS.drone, c = P.chords[Math.min(n, P.chords.length - 1)], t = ctx.currentTime;
      voices.forEach(function (v, i) {
        var f = hz(P.root + c[i % c.length] + (i === 0 ? -12 : 0));
        v.oscs.forEach(function (o) { o.frequency.setTargetAtTime(f, t, 0.8); });
        v.gain.gain.setTargetAtTime(i === 0 ? 0.09 : 0.045, t, 1.5);
      });
      wind.gain.setTargetAtTime(P.wind, t, 2.0);
      chordAt = n;
    }
    function level() {
      if (!ctx) return;
      master.gain.setTargetAtTime(on && preset ? 0.8 : 0, ctx.currentTime, on && preset ? 1.2 : 0.6);
    }
    return {
      toggle: function () {
        on = !on;
        if (on) { init(); ctx.resume(); if (preset) chord(Math.max(chordAt, 0)); }
        level();
        toast(on ? '♪ sound on' + (preset ? '' : ' (no soundtrack on this slide)') : '♪ sound off');
      },
      follow: function (i, s) {
        var sh = (bySlide[i] || []).filter(function (x) { return x.sound; })[0];
        var p = sh ? sh.sound : null;
        if (p !== preset) { preset = p; chordAt = -1; }
        if (on && preset && ctx && s !== chordAt) chord(s);
        level();
      }
    };
  })();

  function toast(text) {
    var t = document.getElementById('lmr-toast');
    if (!t) { t = document.createElement('div'); t.id = 'lmr-toast'; document.body.appendChild(t); }
    t.textContent = text;
    t.classList.add('on');
    clearTimeout(t._h);
    t._h = setTimeout(function () { t.classList.remove('on'); }, 1400);
  }

  PLUGINS.push({
    steps: function (i) { return (bySlide[i] || []).reduce(function (m, sh) { return Math.max(m, sh.nsteps); }, 0); },
    show: show,
    thumb: function (svg, i) {
      // the overview clones the slide's <svg>: give each shader its latest frame
      var src = bySlide[i] || [];
      [].slice.call(svg.querySelectorAll('foreignObject.lmr-shader')).forEach(function (fo, k) {
        var sh = src[k], box = fo.querySelector('.lmr-shader-box');
        if (!sh || !box) return;
        box.innerHTML = '';
        var url = null;
        try { url = sh.gl ? sh.canvas.toDataURL('image/jpeg', 0.7) : (sh.poster ? sh.poster.src : null); } catch (e) { url = null; }
        if (url) { var img = document.createElement('img'); img.className = 'lmr-shader-poster'; img.src = url; box.appendChild(img); }
      });
    },
    key: function (ev) {
      if (ev.key === 'm' && !ev.ctrlKey && !ev.metaKey && !ev.altKey) { ev.preventDefault(); Sound.toggle(); return true; }
      return false;
    }
  });
})();
