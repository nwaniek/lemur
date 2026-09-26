/* Display runtime for build-time SVG decks.
 *
 * Behaviour only — every glyph is already a baked outline, so this just
 * navigates slides, gates step reveals (opacity, honouring data-step /
 * data-until / data-steps), and provides the slide overview (grid 'o' / sidebar 'O',
 * arrow-navigable, Enter/click to jump, Esc to close). Keeps the presenter
 * features of the old viewer without any of its build-time rendering. */
(function () {
  var slides = [].slice.call(document.querySelectorAll('.slide'));
  var nav = document.getElementById('nav');
  var cfg = window.LMR || {};
  var STEP_TRANS = cfg.step || 'fade';          // within-slide: none|fade|rise
  var cur = 0, step = 0;
  // Plugins (e.g. the live-shader player) register before this script runs:
  // { steps(i) → extra steps of slide i, show(i, localStep, jump, slideStep) on every
  //   render, thumb(svgClone, i) for the overview, key(ev) → true if handled }.
  var PLUGINS = window.LMR_PLUGINS || [];
  function pluginSteps(i) {
    return PLUGINS.reduce(function (m, p) { return Math.max(m, p.steps ? p.steps(i) : 0); }, 0);
  }

  // <body data-across=…> drives the CSS across-slide transition; a progress bar
  // is created only when the deck opted in via !progress.
  document.body.setAttribute('data-across', cfg.across || 'none');
  var progress = null;
  if (cfg.progress) {
    progress = document.createElement('div');
    progress.id = 'progress';
    progress.className = cfg.progress;          // 'top' | 'bottom'
    document.body.appendChild(progress);
  }

  /* ---- !anim players ----------------------------------------------------
   * A build-time animation is baked as `.lmr-anim` with a `data-anim` IR blob.
   * The player lerps the keyframe tracks at a time t and writes the results onto
   * the baked <path>s (by data-i); each `self.next()` beat is one slide step, so
   * advancing a step tweens the animation forward in real time. Ported from the
   * wanim runtime (same track/rate maths). */
  var EASE = {
    linear: function (t) { return t; },
    smooth: function (t) { return t * t * t * (10 + t * (-15 + 6 * t)); },
    smoothstep: function (t) { return t * t * (3 - 2 * t); },
    rush_into: function (t) { return 2 * EASE.smooth(t / 2); },
    rush_from: function (t) { return 2 * EASE.smooth(t / 2 + 0.5) - 1; },
    there_and_back: function (t) { return t < 0.5 ? EASE.smooth(2 * t) : EASE.smooth(2 - 2 * t); }
  };
  var clamp01 = function (x) { return x < 0 ? 0 : x > 1 ? 1 : x; };
  function fnum(x) { return Math.round(x * 10000) / 10000; }
  function ahex(rgb) {
    var c = function (v) { var n = Math.round(clamp01(v) * 255).toString(16); return n.length < 2 ? '0' + n : n; };
    return '#' + c(rgb[0]) + c(rgb[1]) + c(rgb[2]);
  }
  function evalTrack(tr, t) {
    var span = tr.t1 - tr.t0, u = span > 1e-9 ? (t - tr.t0) / span : 1;
    u = clamp01(u);
    var alpha = (EASE[tr.r] || EASE.linear)(u), a = tr.a, v = tr.v;
    if (v.length === 1) return v[0];
    var lo = 0, hi = a.length - 1;
    while (lo < hi - 1) { var mid = (lo + hi) >> 1; if (a[mid] <= alpha) lo = mid; else hi = mid; }
    if (tr.s) return alpha >= a[hi] ? v[hi] : v[lo];
    var w = a[hi] - a[lo], fr = w > 1e-9 ? clamp01((alpha - a[lo]) / w) : 1;
    var p = v[lo], q = v[hi], out = new Array(p.length);
    for (var i = 0; i < p.length; i++) out[i] = p[i] + (q[i] - p[i]) * fr;
    return out;
  }
  function valueAt(tracks, t) {
    var chosen = null;
    for (var i = 0; i < tracks.length; i++) { if (tracks[i].t0 <= t + 1e-9) chosen = tracks[i]; else break; }
    return chosen ? evalTrack(chosen, t) : null;
  }
  function apick(bag, prop, t, fallback) {
    var tr = bag[prop];
    return (tr && tr.length) ? valueAt(tr, t) : (fallback || null);
  }
  function lastTrack(tracks, t) {
    var chosen = tracks[0];
    for (var i = 0; i < tracks.length; i++) { if (tracks[i].t0 <= t + 1e-9) chosen = tracks[i]; else break; }
    return chosen;
  }
  function pathData(flat, struct) {
    var counts = struct[0], closed = struct[1], out = '', k = 0;
    if (struct[2]) {                      // a polyline: anchors only (straight segments)
      for (var q = 0; q < counts.length; q++) {
        var m = counts[q];
        for (var j = 0; j < m; j++) out += (j ? 'L' : 'M') + fnum(flat[k + 2 * j]) + ',' + fnum(flat[k + 2 * j + 1]);
        if (m && closed[q]) out += 'Z';
        k += m * 2;
      }
      return out;
    }
    for (var s = 0; s < counts.length; s++) {
      var n = counts[s];
      if (n > 0) {
        out += 'M' + fnum(flat[k]) + ',' + fnum(flat[k + 1]);
        for (var i = 1; i + 2 < n; i += 3) {
          var b = k + i * 2;
          out += 'C' + fnum(flat[b]) + ',' + fnum(flat[b + 1]) + ' ' + fnum(flat[b + 2]) + ',' +
                 fnum(flat[b + 3]) + ' ' + fnum(flat[b + 4]) + ',' + fnum(flat[b + 5]);
        }
        if (closed[s]) out += 'Z';
      }
      k += n * 2;
    }
    return out;
  }
  function applyDraw(el, dr, len, dash, scale) {
    var a = dr ? dr[0] : 0, b = dr ? dr[1] : 1;
    if (b - a < 1e-4) {                 // nothing drawn yet: no stroke, so a round
      el.setAttribute('stroke', 'none'); // cap can't leave a dot at the start point
      el.removeAttribute('stroke-dasharray');
      el.removeAttribute('stroke-dashoffset');
      return;
    }
    if (a <= 0.0001 && b >= 0.9999) {
      if (dash) el.setAttribute('stroke-dasharray', dash.map(function (x) { return fnum(x / (scale || 1)); }).join(' '));
      else el.removeAttribute('stroke-dasharray');
      el.removeAttribute('stroke-dashoffset');
      return;
    }
    var L = len || 1, drawn = Math.max(0, b - a) * L;
    el.setAttribute('stroke-dasharray', fnum(drawn) + ' ' + fnum(L + 1));
    el.setAttribute('stroke-dashoffset', fnum(-a * L));
  }

  function AnimPlayer(el) {
    var self = this;
    this.root = el;              // the `.lmr-anim` group (hidden until first apply)
    this.data = JSON.parse(el.getAttribute('data-anim'));
    this.beats = this.data.beats || [];
    this.vp = this.data.vp; this.ppu = this.data.ppu; this.asp = this.data.asp; this.fh0 = this.data.fh0;
    this.cam = el.querySelector('.anim-cam');
    this.paths = {}; this.node = {}; this.byNode = {};
    el.querySelectorAll('[data-i]').forEach(function (p) { self.paths[+p.getAttribute('data-i')] = p; });
    (this.data.nodes || []).forEach(function (nd) { self.node[nd.i] = nd; });
    (this.data.tracks || []).forEach(function (tr) {
      var bag = self.byNode[tr.n] = self.byNode[tr.n] || {};
      (bag[tr.p] = bag[tr.p] || []).push(tr);
    });
    for (var n in this.byNode) for (var p in this.byNode[n])
      this.byNode[n][p].sort(function (x, y) { return x.t0 - y.t0; });
    this.views = this.data.views || [];
    this.t = 0; this.target = 0; this.raf = 0;
  }
  // View k's camera at time t (the angles may move; the rest is fixed).
  AnimPlayer.prototype.viewCam = function (k, t) {
    var v = this.views[k], ae = (v.ae && v.ae.length ? valueAt(v.ae, t) : null) || v.ae0;
    return { a: ae[0], e: ae[1], s: v.s, c: v.c, o: v.o, p: v.p };
  };
  AnimPlayer.prototype.steps = function () { return this.beats.length; };
  AnimPlayer.prototype.busy = function () { return !!this.raf; };
  AnimPlayer.prototype.finish = function () {   // snap a running tween to its target
    if (this.raf) { cancelAnimationFrame(this.raf); this.raf = 0; }
    this.t = this.target; this.apply(this.target);
  };
  AnimPlayer.prototype.seek = function (localStep, animate) {
    var target = localStep <= 0 ? 0 : this.beats[Math.min(localStep, this.beats.length) - 1];
    this.target = target;
    if (this.raf) { cancelAnimationFrame(this.raf); this.raf = 0; }
    if (!animate) { this.t = target; this.apply(target); return; }
    // Tween by real time *elapsed since the first frame* — never a delta measured
    // from the moment the key was pressed, which could be a whole beat and flash a
    // near-final frame on frame one. `start` is fixed on the first callback, so
    // frame one is dt=0 (the current state) and playback grows smoothly from there.
    var self = this, from = this.t, dir = target >= from ? 1 : -1, start = null;
    var frame = function (now) {
      if (start === null) start = now;
      var t = from + dir * (now - start) / 1000;
      if ((dir > 0 && t >= target) || (dir < 0 && t <= target)) {
        self.t = target; self.apply(target); self.raf = 0; return;
      }
      self.t = t; self.apply(t);
      self.raf = requestAnimationFrame(frame);
    };
    this.raf = requestAnimationFrame(frame);
  };
  AnimPlayer.prototype.applyCamera = function (t) {
    var cam = this.data.camera || [], v = null;
    for (var i = 0; i < cam.length; i++) { if (cam[i].t0 <= t + 1e-9) v = evalTrack(cam[i], t); else break; }
    var cx = v ? v[0] : 0, cy = v ? v[1] : 0, fh = v ? v[2] : this.fh0;
    var vp = this.vp, s = Math.min(vp[2] / (fh * this.asp), vp[3] / fh);
    this.cam.setAttribute('transform', 'matrix(' + fnum(s) + ',0,0,' + fnum(-s) + ',' +
      fnum(vp[0] + vp[2] / 2 - s * cx) + ',' + fnum(vp[1] + vp[3] / 2 + s * cy) + ')');
  };
  AnimPlayer.prototype.apply = function (t) {
    this.applyCamera(t);
    this.root.style.visibility = 'visible';   // we now have a real frame — reveal it

    // 3-D world shapes: projected with window.LMRW (svg/world.js, inlined when a
    // deck has any)
    var LMRW = window.LMRW, cams = [];
    if (LMRW) for (var k = 0; k < this.views.length; k++) cams.push(this.viewCam(k, t));
    for (var i in this.paths) {
      var node = this.node[i], el = this.paths[i], bag = this.byNode[i] || {}, st = node.s || {};
      var vis = apick(bag, 'v', t, st.v);
      if (vis && vis[0] < 0.5) { el.style.display = 'none'; continue; }
      var cam = (node.w !== undefined && cams.length) ? cams[node.w] : null, occ = cam ? this.views[node.w].occ : null;
      var dim = 1, len = node.len || 0;
      if (cam) {                            // a world shape: the player projects it
        var g3 = apick(bag, 'g3', t, st.g3);
        if (g3 && LMRW.occludes(occ, cam, g3[0], g3[1], g3[2])) dim = node.ga === undefined ? 0.3 : node.ga;
      }
      if (cam && node.wk === 'anchor') {
        var a3 = apick(bag, 'a3', t, st.a3), hid = a3 && LMRW.occludes(occ, cam, a3[0], a3[1], a3[2]);
        if (hid && node.wr === 'hide') { el.style.display = 'none'; continue; }
        if (hid && node.wr === 'ghost') dim *= node.ga === undefined ? 0.3 : node.ga;
      }
      if (cam && node.wr === 'cull') {
        var nr = node.nrm, tw = LMRW.toward(cam);
        if (!(nr[0] * tw[0] + nr[1] * tw[1] + nr[2] * tw[2] > 0)) { el.style.display = 'none'; continue; }
      }
      el.style.display = '';
      var scale = 1, tm = apick(bag, 't', t, st.t);
      if (cam && node.wk === 'anchor' && a3) {
        var pa = LMRW.project(cam, a3[0], a3[1], a3[2]);
        tm = (tm || [1, 0, 0, 1, 0, 0]).slice(); tm[4] += pa[0]; tm[5] += pa[1];
      }
      if (tm) { el.setAttribute('transform', 'matrix(' + tm.map(fnum).join(' ') + ')'); scale = Math.hypot(tm[0], tm[1]) || 1; }
      if (cam && node.k === 'w') {
        var dl = LMRW.d(LMRW.paths(node.wk, node.wr, occ, cam, apick(bag, 'p3', t, st.p3) || [], node.struct || [[], []]));
        if (!dl[0]) { el.style.display = 'none'; continue; }   // nothing of it on this side
        el.setAttribute('d', dl[0]); len = dl[1];
      } else {
        var d = bag.d ? valueAt(bag.d, t) : null;
        if (d) el.setAttribute('d', pathData(d, lastTrack(bag.d, t).struct));
      }
      var fo = apick(bag, 'fo', t, st.fo), fc = apick(bag, 'fc', t, st.fc);
      if (dim < 1) { fo = fo && [fo[0] * dim]; }
      if (fo && fo[0] > 0.001) { el.setAttribute('fill', fc ? ahex(fc) : '#fff'); el.setAttribute('fill-opacity', fnum(fo[0])); }
      else el.setAttribute('fill', 'none');
      var so = apick(bag, 'so', t, st.so), sw = apick(bag, 'sw', t, st.sw), sc = apick(bag, 'sc', t, st.sc);
      if (dim < 1) { so = so && [so[0] * dim]; }
      if (so && sw && so[0] > 0.001 && sw[0] > 1e-4) {
        el.setAttribute('stroke', sc ? ahex(sc) : '#fff');
        el.setAttribute('stroke-opacity', fnum(so[0]));
        el.setAttribute('stroke-width', (sw[0] / this.ppu / scale).toPrecision(5));
      } else el.setAttribute('stroke', 'none');
      applyDraw(el, apick(bag, 'dr', t, st.dr), len, node.dash, scale);
    }
  };

  var players = slides.map(function (s) {
    return [].slice.call(s.querySelectorAll('.lmr-anim')).map(function (el) { return new AnimPlayer(el); });
  });
  // A gated element is visible on step s when s is in its gate: one interval
  // (data-step[/data-until]) or several (data-steps="1-2,4-", an open end = on).
  function visibleAt(e, s) {
    var ss = e.getAttribute('data-steps');
    if (ss !== null) {
      return ss.split(',').some(function (t) {
        var p = t.split('-'), a = +p[0], u = (p[1] === undefined || p[1] === '') ? Infinity : +p[1];
        return t !== '' && s >= a && s <= u;
      });
    }
    var a = +e.getAttribute('data-step'), u = e.getAttribute('data-until');
    return s >= a && (u === null || s <= +u);
  }
  // The largest step number an element references — a slide has as many steps
  // as the largest number used on it (a bounded `<1-3>` still needs step 3).
  function stepMax(e) {
    var m = +e.getAttribute('data-step') || 0, u = e.getAttribute('data-until'),
        ss = e.getAttribute('data-steps');
    if (u !== null) m = Math.max(m, +u);
    if (ss) (ss.match(/\d+/g) || []).forEach(function (n) { m = Math.max(m, +n); });
    return m;
  }
  function animBase(i) {       // reveals step first; the animation plays after them
    var m = 0;
    slides[i].querySelectorAll('[data-step]').forEach(function (e) { m = Math.max(m, stepMax(e)); });
    return m;
  }
  function animSteps(i) {
    return players[i].reduce(function (m, p) { return Math.max(m, p.steps()); }, 0);
  }

  function maxOf(i) { return animBase(i) + Math.max(animSteps(i), pluginSteps(i)); }

  var LABELS = (window.LMR && window.LMR.labels) || {};

  function updateHash() {
    var h = '#/' + (cur + 1) + (step > 0 ? '/' + step : '');
    if (location.hash !== h) history.replaceState(null, '', h);  // no hashchange, no loop
  }

  function fromHash() {
    var m = (location.hash || '').replace(/^#\/?/, '');
    if (!m) return false;
    var parts = m.split('/'), key = parts[0], st = parts[1] ? +parts[1] : 0;
    var idx = /^\d+$/.test(key) ? (+key - 1) : (LABELS[key] !== undefined ? LABELS[key] - 1 : null);
    if (idx === null || isNaN(idx)) return false;
    cur = Math.max(0, Math.min(slides.length - 1, idx));
    step = Math.max(0, Math.min(st || 0, maxOf(cur)));
    return true;
  }

  var shown = null;   // last-rendered slide index, to cut multi-slide jumps
  var shownStep = 0;

  function render() {
    // suppress motion on the first paint and on a multi-slide jump (cut, don't
    // travel/fade) — for one reflow, so nothing animates in from its parked spot
    if (shown === null || Math.abs(cur - shown) > 1) {
      document.body.classList.add('no-anim');
      void document.body.offsetWidth;                       // force a reflow
      requestAnimationFrame(function () { document.body.classList.remove('no-anim'); });
    }
    slides.forEach(function (s, i) {
      s.classList.remove('is-current', 'is-before', 'is-after', 'is-out');
      s.classList.add(i === cur ? 'is-current' : (i < cur ? 'is-before' : 'is-after'));
    });
    if (shown !== null && shown !== cur) slides[shown].classList.add('is-out');  // travels out
    slides[cur].querySelectorAll('[data-step]').forEach(function (e) {
      var on = visibleAt(e, step);
      e.style.opacity = on ? '1' : '0';
      if (STEP_TRANS === 'rise') e.style.transform = on ? 'none' : 'translateY(12px)';
    });
    if (nav) {
      var more = step < maxOf(cur);                 // the slide still has sub-steps
      nav.classList.toggle('at-start', cur === 0 && step === 0);
      nav.classList.toggle('at-end', cur === slides.length - 1 && !more);
      nav.dataset.more = more ? 'step' : 'slide';   // cue Next in the accent colour
    }
    if (progress) {
      var total = slides.length, frac = total > 1 ? (cur + (maxOf(cur) ? step / maxOf(cur) : 0)) / (total - 1) : 1;
      progress.style.transform = 'scaleX(' + Math.max(0, Math.min(1, frac)) + ')';
    }
    // Drive this slide's animations. Each beat is a step past the reveal steps;
    // a single step change on the same slide tweens, a jump snaps.
    if (players[cur].length) {
      var base = animBase(cur);
      var jump = shown !== cur || Math.abs(step - shownStep) > 1;
      players[cur].forEach(function (p) {
        p.seek(Math.max(0, Math.min(step - base, p.steps())), !jump);
      });
    }
    var pjump = shown !== cur || Math.abs(step - shownStep) > 1;
    PLUGINS.forEach(function (p) { if (p.show) p.show(cur, Math.max(0, step - animBase(cur)), pjump, step); });
    shown = cur;
    shownStep = step;
    updateHash();
  }

  function go(i, s) {
    cur = Math.max(0, Math.min(slides.length - 1, i));
    step = s || 0;
    render();
  }
  // A press while an animation is still playing completes it (skip the wait)
  // instead of navigating — so you can always step through a deck at your pace.
  function anims() { return players[cur] || []; }
  function busy() { return anims().some(function (p) { return p.busy(); }); }
  function settle() { anims().forEach(function (p) { p.finish(); }); }
  function fwd() {
    if (busy()) { settle(); return; }
    if (step < maxOf(cur)) step++; else if (cur < slides.length - 1) { cur++; step = 0; }
    render();
  }
  function back() {
    if (busy()) { settle(); return; }
    if (step > 0) step--; else if (cur > 0) { cur--; step = maxOf(cur); }
    render();
  }

  /* ---- overview ---------------------------------------------------------- */
  var ov = null, mode = null, sel = 0, resizer = null;

  try {                                   // restore a remembered sidebar width
    var w0 = localStorage.getItem('lmr-sidebar-w');
    if (w0) document.documentElement.style.setProperty('--sidebar-w', w0 + 'px');
  } catch (e) { /* */ }

  function wireResizer() {
    resizer = document.createElement('div');
    resizer.id = 'ov-resizer';
    var setW = function (px) {
      var w = Math.max(200, Math.min(px, window.innerWidth * 0.6));
      document.documentElement.style.setProperty('--sidebar-w', w + 'px');
      try { localStorage.setItem('lmr-sidebar-w', String(Math.round(w))); } catch (e) { /* */ }
    };
    resizer.addEventListener('pointerdown', function (e) {
      if (mode !== 'sidebar') return;
      e.preventDefault();
      resizer.setPointerCapture(e.pointerId);
      document.body.classList.add('ov-resizing');
      var move = function (ev) { setW(ev.clientX); };
      var up = function () {
        document.body.classList.remove('ov-resizing');
        resizer.removeEventListener('pointermove', move);
        resizer.removeEventListener('pointerup', up);
        resizer.removeEventListener('pointercancel', up);
      };
      resizer.addEventListener('pointermove', move);
      resizer.addEventListener('pointerup', up);
      resizer.addEventListener('pointercancel', up);
    });
    document.body.appendChild(resizer);
  }

  function buildOverview() {
    ov = document.createElement('div');
    ov.id = 'ov';
    var grid = document.createElement('div');
    grid.id = 'ov-grid';
    slides.forEach(function (s, i) {
      var t = document.createElement('div');
      t.className = 'thumb';
      var svg = s.querySelector('svg').cloneNode(true);
      svg.removeAttribute('id');
      var defs = svg.querySelector('defs');
      if (defs) defs.remove();  // <use> resolves to the originals' global ids
      svg.querySelectorAll('[data-step]').forEach(function (g) {   // the slide's end state
        g.style.opacity = '';
        g.style.transform = '';
        g.setAttribute('opacity', g.getAttribute('data-final') === '0' ? '0' : '1');
      });
      PLUGINS.forEach(function (p) { if (p.thumb) p.thumb(svg, i); });
      t.appendChild(svg);
      var n = document.createElement('div');
      n.className = 'n';
      n.textContent = (i + 1);
      t.appendChild(n);
      t.addEventListener('click', function (e) { e.stopPropagation(); pick(i); });
      grid.appendChild(t);
    });
    ov.appendChild(grid);
    ov.addEventListener('click', function (e) { e.stopPropagation(); closeOverview(); });
    document.body.appendChild(ov);
    wireResizer();
  }

  function openOverview(m) {
    if (!ov) buildOverview();
    mode = m;
    sel = cur;
    ov.className = m;                 // 'grid' | 'sidebar'
    ov.style.display = 'block';
    resizer.style.display = (m === 'sidebar') ? 'block' : 'none';
    document.body.classList.toggle('ov-sidebar', m === 'sidebar');
    ov.querySelectorAll('.thumb').forEach(function (t, i) { t.classList.toggle('cur', i === cur); });
    updateSel();
  }
  function closeOverview() {
    if (!ov) return;
    ov.style.display = 'none';
    if (resizer) resizer.style.display = 'none';
    mode = null;
    document.body.classList.remove('ov-sidebar');
  }
  function pick(i) { closeOverview(); go(i, 0); }

  function updateSel() {
    var thumbs = ov.querySelectorAll('.thumb');
    thumbs.forEach(function (t, i) { t.classList.toggle('sel', i === sel); });
    if (thumbs[sel]) thumbs[sel].scrollIntoView({ block: 'nearest' });
  }

  /* Move the grid selection to the geometrically-nearest thumb (like the old
   * viewer's slide sorter). */
  function gridMove(key) {
    var thumbs = [].slice.call(ov.querySelectorAll('.thumb'));
    var c = thumbs[sel];
    if (!c) return;
    var cr = c.getBoundingClientRect(), cx = cr.left + cr.width / 2, cy = cr.top + cr.height / 2;
    var horiz = key === 'ArrowRight' || key === 'ArrowLeft';
    var best = -1, score = Infinity;
    thumbs.forEach(function (t, i) {
      if (i === sel) return;
      var r = t.getBoundingClientRect(), dx = r.left + r.width / 2 - cx, dy = r.top + r.height / 2 - cy;
      if (key === 'ArrowRight' && dx <= 1) return;
      if (key === 'ArrowLeft' && dx >= -1) return;
      if (key === 'ArrowDown' && dy <= 1) return;
      if (key === 'ArrowUp' && dy >= -1) return;
      var along = horiz ? Math.abs(dx) : Math.abs(dy);
      var cross = horiz ? Math.abs(dy) : Math.abs(dx);
      var sc = along + cross * 3;    // prefer the same row/column
      if (sc < score) { score = sc; best = i; }
    });
    if (best >= 0) { sel = best; updateSel(); }
  }

  addEventListener('keydown', function (ev) {
    if (!mode && PLUGINS.some(function (p) { return p.key && p.key(ev); })) return;
    if (mode) {
      switch (ev.key) {
        case 'ArrowRight': case 'ArrowLeft': case 'ArrowUp': case 'ArrowDown':
          ev.preventDefault(); gridMove(ev.key); return;
        case 'Home': sel = 0; updateSel(); return;
        case 'End': sel = slides.length - 1; updateSel(); return;
        case 'Enter': case ' ': ev.preventDefault(); pick(sel); return;
        case 'o': case 'O': case 'Escape': ev.preventDefault(); closeOverview(); return;
        default: return;
      }
    }
    switch (ev.key) {
      case ' ': case 'ArrowRight': case 'PageDown': ev.preventDefault(); fwd(); break;
      case 'ArrowLeft': case 'PageUp': ev.preventDefault(); back(); break;
      case 'ArrowDown': ev.preventDefault(); go(cur + 1, 0); break;
      case 'ArrowUp': ev.preventDefault(); go(cur - 1, 0); break;
      case 'Home': ev.preventDefault(); go(0, 0); break;
      case 'End': ev.preventDefault(); go(slides.length - 1, maxOf(slides.length - 1)); break;
      case 'o': ev.preventDefault(); openOverview('grid'); break;
      case 'O': ev.preventDefault(); openOverview('sidebar'); break;
    }
  });
  document.addEventListener('click', function () { if (!mode) fwd(); });
  var wheelAt = 0;                                  // throttle: one notch = one step
  addEventListener('wheel', function (ev) {
    if (mode || ev.ctrlKey || ev.metaKey || !ev.deltaY) return;   // let the overview scroll
    ev.preventDefault();
    var now = Date.now();
    if (now - wheelAt < 120) return;
    wheelAt = now;
    if (ev.deltaY > 0) fwd(); else back();
  }, { passive: false });
  if (nav) {
    var stop = function (fn) {
      return function (ev) { ev.stopPropagation(); ev.preventDefault(); fn(); };
    };
    nav.querySelector('.nav-prev').addEventListener('click', stop(back));
    nav.querySelector('.nav-next').addEventListener('click', stop(fwd));
  }
  addEventListener('hashchange', function () { if (fromHash()) render(); });

  fromHash();   // deep-link: #/<slide>[/<step>] or #/<label>
  render();
})();
