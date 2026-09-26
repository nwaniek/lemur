/* WebGPU compute for lemur SVG decks (`!compute` blocks): a plugin of the
 * display runtime (registered in window.LMR_PLUGINS before runtime.js runs).
 *
 * Each `<foreignObject class="lmr-compute" data-wgsl=… data-manifest=…>` holds
 * a WGSL program and what the build read out of it (lemur/wgsl.py): storage
 * buffers with their sizes, compute kernels in order with their workgroup
 * counts (`once` kernels initialise, the others run every tick), and a line map
 * for error messages. The player adds `lmr` (a uniform: time, dt, step, …), the
 * `lmr_hash`/`lmr_rand` helpers, and a full-screen pass that calls
 * `mainImage(fragCoord) -> vec4f` (keep PRELUDE/TAIL in step with wgsl.py).
 *
 * A simulation has a history, and a talk goes back and jumps around, so:
 *   - it runs with a fixed timestep (`!rate` ticks per second) and a seed, so a
 *     run is repeatable;
 *   - its buffers are snapshotted whenever a step is entered, and going back
 *     restores that snapshot;
 *   - a jump ahead (a reload, the overview) replays the missing steps, `!warmup`
 *     seconds of simulation each, taking snapshots on the way.
 * One GPU device serves the whole deck; a slide keeps its state while you are
 * elsewhere, and only the slide on screen runs. */
(function () {
  var PLUGINS = window.LMR_PLUGINS = window.LMR_PLUGINS || [];
  var slides = [].slice.call(document.querySelectorAll('.slide'));

  var PRELUDE = 'struct Lemur {\n' +
    '  mouse: vec4f, resolution: vec2f, time: f32, dt: f32,\n' +
    '  step: f32, steps: f32, step_raw: u32, frame: u32, tick: u32, seed: u32,\n' +
    '}\n' +
    '@group(0) @binding(0) var<uniform> lmr: Lemur;\n' +
    'fn lmr_hash(x: u32) -> u32 {\n' +
    '  let s = x * 747796405u + 2891336453u;\n' +
    '  let w = ((s >> ((s >> 28u) + 4u)) ^ s) * 277803737u;\n' +
    '  return (w >> 22u) ^ w;\n' +
    '}\n' +
    'fn lmr_rand(x: u32) -> f32 { return f32(lmr_hash(x)) / 4294967296.0; }\n';
  var PRELUDE_LINES = PRELUDE.split('\n').length - 1;
  var TAIL = '\n@vertex fn lmr_vs(@builtin(vertex_index) i: u32) -> @builtin(position) vec4f {\n' +
    '  let p = vec2f(f32((i << 1u) & 2u), f32(i & 2u));\n' +
    '  return vec4f(p * 2.0 - 1.0, 0.0, 1.0);\n' +
    '}\n' +
    '@fragment fn lmr_fs(@builtin(position) p: vec4f) -> @location(0) vec4f {\n' +
    '  let c = mainImage(vec2f(p.x, lmr.resolution.y - p.y));\n' +
    '  return vec4f(c.rgb, 1.0);\n' +
    '}\n';
  var NO_GPU = 'This slide runs a WebGPU compute shader, and this browser does not offer WebGPU.\n\n' +
    'Current Chrome, Edge and Safari do (on Linux, Chrome may need chrome://flags → ' +
    '"Unsafe WebGPU Support"); Firefox does on Windows.';

  function decode(b64) {
    var bin = atob(b64), bytes = new Uint8Array(bin.length);
    for (var i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
    return new TextDecoder('utf-8').decode(bytes);
  }

  // one device for the whole deck (null: no WebGPU)
  var devicePromise = null;
  function getDevice() {
    if (devicePromise) return devicePromise;
    devicePromise = (async function () {
      if (!navigator.gpu) return null;
      var adapter = await navigator.gpu.requestAdapter({ powerPreference: 'high-performance' });
      if (!adapter) return null;
      var dev = await adapter.requestDevice();
      dev.lost.then(function (info) {
        if (window.console) console.warn('lemur !compute: the GPU device was lost (' + info.reason + '): ' + info.message);
        devicePromise = null;
        bySlide.forEach(function (l) { l.forEach(function (c) { c.lost(info); }); });
      });
      dev.addEventListener('uncapturederror', function (ev) {
        if (window.console) console.warn('lemur !compute: ' + ev.error.message);
      });
      return dev;
    })().catch(function () { return null; });
    return devicePromise;
  }

  function Compute(fo) {
    this.fo = fo;
    this.box = fo.querySelector('.lmr-compute-box');
    this.src = decode(fo.getAttribute('data-wgsl'));
    this.man = JSON.parse(fo.getAttribute('data-manifest'));
    var st = fo.getAttribute('data-steps') || '0';
    this.follow = st === 'slide';               // the slide's own step, not steps of its own
    this.nsteps = this.follow ? 0 : +st;
    this.rate = Math.max(1, +(fo.getAttribute('data-rate') || 60));
    this.seed = (+(fo.getAttribute('data-seed') || 1)) >>> 0;
    this.warmup = Math.max(0, +(fo.getAttribute('data-warmup') || 2));
    var q = parseFloat(fo.getAttribute('data-quality') || '1');
    this.scale = isFinite(q) && q > 0 ? Math.min(q, 2) : 1;
    this.mouse = [0, 0, 0, 0];
    this.ready = false; this.failed = false; this.running = false;
    this.stepTarget = 0; this.stepNow = 0; this.stepEntered = -1;
    this.tickN = 0; this.frameN = 0; this.acc = 0;
    this.snaps = {};
    this.poster = null;
  }

  Compute.prototype.fail = function (msg) {
    this.box.innerHTML = '';
    var pre = document.createElement('pre');
    pre.className = 'lmr-shader-error';
    pre.textContent = msg;
    this.box.appendChild(pre);
    this.failed = true;
  };

  // a compiler message's line → the author's file and line
  Compute.prototype.where = function (line) {
    var n = line - PRELUDE_LINES, runs = this.man.lines || [], k = 0;
    if (n < 1) return 'lemur prelude';
    for (var i = 0; i < runs.length; i++) {
      if (n <= k + runs[i][2]) return (this.man.files[runs[i][0]] || '?') + ':' + (runs[i][1] + n - k - 1);
      k += runs[i][2];
    }
    return 'line ' + n;
  };

  Compute.prototype.init = async function () {
    if (this.ready || this.failed || this.initing) return this.ready;
    this.initing = true;
    var dev = await getDevice();
    this.initing = false;
    if (!dev) { this.fail(NO_GPU); return false; }
    this.dev = dev;
    var self = this, man = this.man;
    var module = dev.createShaderModule({ code: PRELUDE + this.src + TAIL });
    var info = await module.getCompilationInfo();
    var errs = info.messages.filter(function (m) { return m.type === 'error'; });
    if (errs.length) {
      this.fail('WGSL error:\n' + errs.map(function (m) { return self.where(m.lineNum) + ': ' + m.message; }).join('\n'));
      return false;
    }
    dev.pushErrorScope('validation');
    var entries = [{ binding: 0, visibility: GPUShaderStage.COMPUTE | GPUShaderStage.FRAGMENT, buffer: { type: 'uniform' } }];
    man.buffers.forEach(function (b) {
      entries.push({ binding: b.binding, visibility: GPUShaderStage.COMPUTE | GPUShaderStage.FRAGMENT,
                     buffer: { type: b.access === 'read' ? 'read-only-storage' : 'storage' } });
    });
    var bgl = dev.createBindGroupLayout({ entries: entries });
    var layout = dev.createPipelineLayout({ bindGroupLayouts: [bgl] });
    this.ubuf = dev.createBuffer({ size: 64, usage: GPUBufferUsage.UNIFORM | GPUBufferUsage.COPY_DST });
    this.bufs = man.buffers.map(function (b) {
      return dev.createBuffer({ size: Math.max(4, b.size),
                                usage: GPUBufferUsage.STORAGE | GPUBufferUsage.COPY_SRC | GPUBufferUsage.COPY_DST });
    });
    this.bindGroup = dev.createBindGroup({ layout: bgl, entries: [{ binding: 0, resource: { buffer: this.ubuf } }].concat(
      man.buffers.map(function (b, i) { return { binding: b.binding, resource: { buffer: self.bufs[i] } }; })) });
    this.kernels = man.kernels.map(function (k) {
      return { once: k.once, groups: k.groups, name: k.name,
               pipe: dev.createComputePipeline({ layout: layout, compute: { module: module, entryPoint: k.name } }) };
    });
    this.format = navigator.gpu.getPreferredCanvasFormat();
    this.drawPipe = dev.createRenderPipeline({
      layout: layout,
      vertex: { module: module, entryPoint: 'lmr_vs' },
      fragment: { module: module, entryPoint: 'lmr_fs', targets: [{ format: this.format }] },
      primitive: { topology: 'triangle-list' }
    });
    var err = await dev.popErrorScope();
    if (err) { this.fail('WebGPU error:\n' + err.message); return false; }
    this.uniforms = new ArrayBuffer(64);
    this.uf = new Float32Array(this.uniforms);
    this.uu = new Uint32Array(this.uniforms);
    this.ready = true;
    this.reset();
    return true;
  };

  // the device is gone (a driver reset, the GPU process restarted): start over on
  // a new one and replay to where the talk is, a few times at most
  Compute.prototype.lost = function (info) {
    var wasRunning = this.running, step = this.stepTarget;
    this.ready = false; this.running = false; this.canvas = null; this.ctx = null;
    this.snaps = {}; this.stepEntered = -1;
    this.box.innerHTML = '';
    this.retries = (this.retries || 0) + 1;
    if (this.retries > 3) { this.fail('The GPU device was lost: ' + ((info && info.message) || 'unknown reason')); return; }
    if (wasRunning) {
      var self = this;
      this.pending = { step: step, jump: true };
      setTimeout(function () { if (!self.running) self.start(); }, 300);
    }
  };

  Compute.prototype.writeUniforms = function (step) {
    var f = this.uf, u = this.uu, c = this.canvas;
    f[0] = this.mouse[0]; f[1] = this.mouse[1]; f[2] = this.mouse[2]; f[3] = this.mouse[3];
    f[4] = c ? c.width : 1; f[5] = c ? c.height : 1;
    f[6] = this.tickN / this.rate; f[7] = 1 / this.rate;
    f[8] = step; f[9] = this.nsteps;
    u[10] = Math.round(this.follow ? step : Math.min(this.stepTarget, this.nsteps));
    u[11] = this.frameN; u[12] = this.tickN; u[13] = this.seed;
    this.dev.queue.writeBuffer(this.ubuf, 0, this.uniforms);
  };

  Compute.prototype.runKernels = function (once) {
    var enc = this.dev.createCommandEncoder(), self = this;
    this.kernels.forEach(function (k) {
      if (k.once !== once) return;
      var pass = enc.beginComputePass();
      pass.setPipeline(k.pipe);
      pass.setBindGroup(0, self.bindGroup);
      pass.dispatchWorkgroups(k.groups[0], k.groups[1], k.groups[2]);
      pass.end();
    });
    this.dev.queue.submit([enc.finish()]);
  };

  Compute.prototype.reset = function () {
    var enc = this.dev.createCommandEncoder();
    this.bufs.forEach(function (b) { enc.clearBuffer(b); });
    this.dev.queue.submit([enc.finish()]);
    this.tickN = 0; this.acc = 0;
    this.writeUniforms(0);
    this.runKernels(true);
  };

  Compute.prototype.tick = function (step) {
    this.writeUniforms(step);
    this.runKernels(false);
    this.tickN++;
  };

  Compute.prototype.snapshot = function (k) {
    var dev = this.dev, enc = dev.createCommandEncoder(), s = this.snaps[k];
    if (!s) {
      s = this.snaps[k] = { bufs: this.bufs.map(function (b) {
        return dev.createBuffer({ size: b.size, usage: GPUBufferUsage.COPY_SRC | GPUBufferUsage.COPY_DST });
      }) };
    }
    this.bufs.forEach(function (b, i) { enc.copyBufferToBuffer(b, 0, s.bufs[i], 0, b.size); });
    dev.queue.submit([enc.finish()]);
    s.tick = this.tickN; s.stepNow = this.stepNow;
  };

  Compute.prototype.restore = function (k) {
    var s = this.snaps[k], enc = this.dev.createCommandEncoder(), self = this;
    s.bufs.forEach(function (b, i) { enc.copyBufferToBuffer(b, 0, self.bufs[i], 0, b.size); });
    this.dev.queue.submit([enc.finish()]);
    this.tickN = s.tick; this.stepNow = s.stepNow; this.acc = 0;
  };

  // move the simulation to step `target` (see the header for the rules)
  Compute.prototype.goTo = function (target, jump) {
    if (!this.ready) { this.stepTarget = target; return; }
    var from = this.stepEntered;
    if (from < 0) { this.snapshot(0); from = this.stepEntered = 0; this.stepNow = 0; }
    if (target === from) { this.stepTarget = target; return; }
    if (target === from + 1 && !jump) {         // an ordinary keypress forward
      this.stepTarget = target;
      this.snapshot(target);
      this.stepEntered = target;
      return;
    }
    if (this.snaps[target]) {                   // back (or a jump to a step we have seen)
      this.restore(target);
      this.stepTarget = target; this.stepEntered = target;
      if (jump) this.stepNow = target;
      return;
    }
    // ahead, unseen: replay from the latest snapshot below `target`
    var base = 0;
    for (var k in this.snaps) if (+k < target && +k > base) base = +k;
    this.restore(base);
    var n = Math.round(this.warmup * this.rate);
    for (var j = base; j < target; j++) {
      this.stepNow = j;
      for (var t = 0; t < n; t++) this.tick(j);
      this.stepNow = j + 1;
      this.snapshot(j + 1);
    }
    this.stepTarget = target; this.stepEntered = target; this.stepNow = target;
  };

  Compute.prototype.start = async function () {
    if (this.failed) return;
    if (!(await this.init())) return;
    if (!this.canvas) {
      var c = document.createElement('canvas');
      c.className = 'lmr-shader-canvas';
      this.box.innerHTML = '';
      this.box.appendChild(c);
      this.canvas = c;
      this.ctx = c.getContext('webgpu');
      this.configured = null;
      var self = this;
      c.addEventListener('pointermove', function (ev) {
        var r = c.getBoundingClientRect();
        self.mouse[0] = (ev.clientX - r.left) / r.width * c.width;
        self.mouse[1] = (1 - (ev.clientY - r.top) / r.height) * c.height;
      });
    }
    this.running = true;
    this.thaw();
    var go = this.pending || { step: this.stepTarget, jump: true };
    this.pending = undefined;
    this.goTo(go.step, go.jump);
  };

  // a still of the current frame, laid over the canvas (for print, the
  // overview, and while the slide is not shown)
  Compute.prototype.freeze = function () {
    if (!this.ready || !this.canvas) return;
    try {
      this.render();                            // a WebGPU canvas is readable only in the task that drew it
      var url = this.canvas.toDataURL('image/jpeg', 0.85);
      if (!this.poster) {
        this.poster = document.createElement('img');
        this.poster.className = 'lmr-shader-poster';
      }
      this.poster.src = url;
      if (this.poster.parentNode !== this.box) this.box.appendChild(this.poster);
    } catch (e) { /* keep whatever still we had */ }
  };

  Compute.prototype.thaw = function () {
    if (this.poster && this.poster.parentNode) this.poster.parentNode.removeChild(this.poster);
  };

  Compute.prototype.stop = function () {
    if (!this.running) return;
    this.freeze();
    this.running = false;
  };

  Compute.prototype.render = function () {
    var c = this.canvas, dev = this.dev;
    var r = c.getBoundingClientRect();
    if (r.width < 2 || r.height < 2) return;
    var dpr = Math.min(window.devicePixelRatio || 1, 2);
    var w = Math.max(1, Math.round(r.width * dpr * this.scale));
    var h = Math.max(1, Math.round(r.height * dpr * this.scale));
    if (c.width !== w || c.height !== h) { c.width = w; c.height = h; }
    if (this.configured !== this.format) {
      this.ctx.configure({ device: dev, format: this.format, alphaMode: 'opaque' });
      this.configured = this.format;
    }
    this.writeUniforms(this.stepNow);
    var enc = dev.createCommandEncoder();
    var pass = enc.beginRenderPass({ colorAttachments: [{
      view: this.ctx.getCurrentTexture().createView(), loadOp: 'clear', storeOp: 'store',
      clearValue: { r: 0, g: 0, b: 0, a: 1 } }] });
    pass.setPipeline(this.drawPipe);
    pass.setBindGroup(0, this.bindGroup);
    pass.draw(3);
    pass.end();
    dev.queue.submit([enc.finish()]);
    this.frameN++;
  };

  Compute.prototype.frame = function (dt) {
    if (!this.running || !this.ready || !this.canvas) return;
    this.stepNow += (this.stepTarget - this.stepNow) * (1 - Math.exp(-dt / 0.6));
    if (Math.abs(this.stepTarget - this.stepNow) < 1e-4) this.stepNow = this.stepTarget;
    this.acc += dt * this.rate;
    var n = Math.min(Math.floor(this.acc), Math.ceil(this.rate / 30) + 1);   // no spiral of death
    this.acc = Math.min(this.acc - Math.floor(this.acc), 1);
    for (var i = 0; i < n; i++) this.tick(this.stepNow);
    this.render();
  };

  var bySlide = slides.map(function (s) {
    return [].slice.call(s.querySelectorAll('foreignObject.lmr-compute')).map(function (fo) { return new Compute(fo); });
  });
  var active = -1, raf = 0, last = 0;

  function loop(now) {
    raf = requestAnimationFrame(loop);
    var dt = last ? Math.min((now - last) / 1000, 0.1) : 1 / 60;
    last = now;
    (bySlide[active] || []).forEach(function (c) { c.frame(dt); });
  }

  function show(i, localStep, jump, slideStep) {
    if (i !== active) {
      (bySlide[active] || []).forEach(function (c) { c.stop(); });
      active = i;
      (bySlide[i] || []).forEach(function (c) { c.start(); });
      if (!raf && (bySlide[i] || []).length) { last = 0; raf = requestAnimationFrame(loop); }
      if (raf && !(bySlide[i] || []).length) { cancelAnimationFrame(raf); raf = 0; }
    }
    (bySlide[i] || []).forEach(function (c) {
      var s = c.follow ? (slideStep || 0) : Math.min(localStep, c.nsteps);
      if (c.ready && c.running) c.goTo(s, jump);
      else c.pending = { step: s, jump: true };
    });
  }

  addEventListener('beforeprint', function () {
    (bySlide[active] || []).forEach(function (c) { if (c.running) c.freeze(); });
  });
  addEventListener('afterprint', function () {
    (bySlide[active] || []).forEach(function (c) { if (c.running) c.thaw(); });
  });

  PLUGINS.push({
    steps: function (i) { return (bySlide[i] || []).reduce(function (m, c) { return Math.max(m, c.nsteps); }, 0); },
    show: show,
    thumb: function (svg, i) {
      var src = bySlide[i] || [];
      [].slice.call(svg.querySelectorAll('foreignObject.lmr-compute')).forEach(function (fo, k) {
        var c = src[k], box = fo.querySelector('.lmr-compute-box');
        if (!c || !box) return;
        box.innerHTML = '';
        var url = null;
        try {
          if (c.running && c.ready && c.canvas) { c.render(); url = c.canvas.toDataURL('image/jpeg', 0.7); }
          else if (c.poster) url = c.poster.src;
        } catch (e) { url = null; }
        if (url) { var img = document.createElement('img'); img.className = 'lmr-shader-poster'; img.src = url; box.appendChild(img); }
      });
    }
  });
})();
