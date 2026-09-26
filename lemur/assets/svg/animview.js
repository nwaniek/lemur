/* lmranim — the animation viewer (see lemur/animview.py). It drives the deck's
 * animation player (window.LMR_PLAYERS) directly: a timeline to play, scrub
 * and step through beats, an inspector that maps shapes back to the lines of
 * code that made them, a coordinate grid, and the log of the build. State
 * (time, speed, toggles) survives the reload that every rebuild triggers. */
(function () {
  var V = window.LMR_VIEW || {}, KEY = 'lmranim:' + V.file;
  var player = (window.LMR_PLAYERS || []).reduce(function (a, l) { return a.concat(l); }, [])[0];
  if (!player) return;
  // The viewer owns the clock. The deck underneath still reacts to clicks, keys
  // and the wheel by seeking to a beat, and a seek tweens on its own frame loop,
  // which the viewer's pause would never stop: switch deck seeks off.
  player.seek = function () {};
  var dur = Math.max(V.duration || player.data.duration || 0, 1e-6);
  var beats = (V.beats || []).map(function (b) { return typeof b === 'number' ? { t: b } : b; });
  var FRAME = 1 / 30, SPEEDS = [0.1, 0.25, 0.5, 1, 2];
  var st = { t: 0, speed: 3, loop: false, grid: false, vector: false, panel: null, playing: false };
  try { Object.assign(st, JSON.parse(sessionStorage.getItem(KEY) || '{}')); } catch (e) { /* */ }
  st.playing = false;

  // segment boundaries (where animations start and end), for the timeline ticks
  var ticks = {};
  (player.data.tracks || []).forEach(function (tr) { ticks[tr.t0.toFixed(3)] = 1; ticks[tr.t1.toFixed(3)] = 1; });
  ticks = Object.keys(ticks).map(Number);

  // -- chrome ------------------------------------------------------------------------
  function el(tag, attrs, html) {
    var e = document.createElement(tag);
    for (var k in attrs || {}) e.setAttribute(k, attrs[k]);
    if (html !== undefined) e.innerHTML = html;
    return e;
  }
  var bar = el('div', { id: 'av-bar' });
  var row = el('div', { id: 'av-row' });
  var bPlay = el('button', { title: 'play / pause (space)' }, '▶');
  var bLoop = el('button', { title: 'loop the current beat (L)' }, '⟲ beat');
  var bSpeed = el('button', { title: 'speed ([ and ])' }, '1×');
  var num = el('span', { 'class': 'av-num' });
  var beatLbl = el('span', { 'class': 'av-beat' });
  var coord = el('span', { 'class': 'av-dim av-num' });
  var bGrid = el('button', { title: 'coordinate grid (G)' }, 'grid');
  var bVec = el('button', { title: 'show the vector still that print and PDF get (V)' }, 'print view');
  var bShapes = el('button', { title: 'shapes and where your code made them (S)' }, 'shapes');
  var bLog = el('button', { title: 'build log (P)' }, 'log');
  var bHelp = el('button', { title: 'keys (?)' }, '?');
  var info = el('span', { 'class': 'av-dim' }, (V.name || '') + ' · ' + (V.ms / 1000).toFixed(2) + ' s');
  var warn = el('span', { 'class': 'av-warn' }, V.warnings && V.warnings.length ? '⚠ ' + V.warnings.length : '');
  [bPlay, bLoop, bSpeed, el('span', { 'class': 'av-sep' }), num, beatLbl, el('span', { 'class': 'av-grow' }),
   coord, bGrid, bVec, bShapes, bLog, bHelp, el('span', { 'class': 'av-sep' }), info, warn]
    .forEach(function (x) { row.appendChild(x); });
  if (!V.gpu) bVec.style.display = 'none';
  var time = el('div', { id: 'av-time' }), cv = el('canvas');
  time.appendChild(cv);
  bar.appendChild(row); bar.appendChild(time);
  var panel = el('div', { id: 'av-panel' });
  var tip = el('div', { id: 'av-tip' }), toast = el('div', { id: 'av-toast' });
  var help = el('div', { id: 'av-help' }, '<table>' + [
    ['space', 'play / pause'], ['← →', 'a frame back / on'], ['shift ← →', 'the previous / next beat'],
    ['home end', 'the start / the end'], ['L', 'loop the current beat'], ['[ ]', 'slower / faster'],
    ['G', 'coordinate grid (animation units)'], ['V', 'print view: the vector still (GPU views)'],
    ['S', 'shapes: hover to find, click to open the line'], ['P', 'build log and warnings'],
    ['click a shape', 'open the line that made it'], ['wheel', 'scrub'], ['?', 'this help']
  ].map(function (r) { return '<tr><td>' + r[0] + '</td><td>' + r[1] + '</td></tr>'; }).join('') + '</table>');
  [bar, panel, tip, toast, help].forEach(function (x) { document.body.appendChild(x); });
  // a click on the viewer's own controls is theirs alone: it must not reach the
  // deck, whose click handler steps the slide on
  [bar, panel, help].forEach(function (x) {
    x.addEventListener('click', function (ev) { ev.stopPropagation(); });
  });
  var hl = el('div');
  hl.style.cssText = 'position:fixed;z-index:39;pointer-events:none;border:1.5px solid #ffb454;' +
                     'box-shadow:0 0 0 9999px rgba(0,0,0,.06);border-radius:3px;display:none';
  document.body.appendChild(hl);

  function flash(msg, ms) {
    toast.textContent = msg; toast.style.display = 'block';
    clearTimeout(flash.h); if (ms) flash.h = setTimeout(function () { toast.style.display = 'none'; }, ms);
  }
  function save() { try { sessionStorage.setItem(KEY, JSON.stringify(st)); } catch (e) { /* */ } }

  // -- time ------------------------------------------------------------------------
  function beatAt(t) { var k = 0; beats.forEach(function (b, i) { if (t >= b.t - 1e-6) k = i + 1; }); return k; }
  function beatRange(k) {            // beat k plays from the end of beat k-1 to its own time
    return [k > 0 ? beats[k - 1].t : 0, k < beats.length ? beats[k].t : dur];
  }
  function show(t) {
    st.t = Math.max(0, Math.min(dur, t));
    if (player.raf) { cancelAnimationFrame(player.raf); player.raf = 0; }
    player.t = player.target = st.t;
    player.printing = st.vector;
    player.apply(st.t);
    var k = beatAt(st.t);
    num.textContent = st.t.toFixed(2) + ' s / ' + dur.toFixed(2) + ' s';
    var lbl = beats[k] && beats[k].label ? ' · ' + beats[k].label : '';
    beatLbl.textContent = beats.length ? 'beat ' + Math.min(k + 1, beats.length) + ' / ' + beats.length + lbl : 'no beats';
    drawTime();
  }
  var last = 0;
  function tick(now) {
    if (!st.playing) return;
    var dt = last ? Math.min((now - last) / 1000, 0.1) : 0;
    last = now;
    var t = st.t + dt * SPEEDS[st.speed];
    if (st.loop) {
      var r = beatRange(beatAt(Math.max(st.t - 1e-6, 0)));
      if (t >= r[1]) t = r[0];
    } else if (t >= dur) { t = dur; st.playing = false; }
    show(t); refresh();
    if (st.playing) requestAnimationFrame(tick);
  }
  function play(on) {
    st.playing = on === undefined ? !st.playing : on;
    if (st.playing && st.t >= dur - 1e-6 && !st.loop) st.t = 0;
    last = 0; refresh();
    if (st.playing) requestAnimationFrame(tick);
  }
  function stepBeat(dir) {
    var ts = [0].concat(beats.map(function (b) { return b.t; })), t = st.t, i;
    if (dir > 0) { for (i = 0; i < ts.length; i++) if (ts[i] > t + 1e-6) return show(ts[i]); show(dur); }
    else { for (i = ts.length - 1; i >= 0; i--) if (ts[i] < t - 1e-6) return show(ts[i]); show(0); }
  }

  function drawTime() {
    var r = time.getBoundingClientRect(), dpr = window.devicePixelRatio || 1;
    var W = Math.round(r.width * dpr), H = Math.round(r.height * dpr);
    if (cv.width !== W || cv.height !== H) { cv.width = W; cv.height = H; }
    var g = cv.getContext('2d'), x = function (t) { return (t / dur) * W; };
    g.clearRect(0, 0, W, H);
    g.fillStyle = '#1d2229'; g.fillRect(0, H * 0.35, W, H * 0.3);
    if (st.loop) {                                   // the looped beat
      var lr = beatRange(beatAt(Math.max(st.t - 1e-6, 0)));
      g.fillStyle = 'rgba(46,94,110,.45)'; g.fillRect(x(lr[0]), 0, x(lr[1]) - x(lr[0]), H);
    }
    g.fillStyle = '#4a5360';
    ticks.forEach(function (t) { g.fillRect(Math.round(x(t)), H * 0.3, dpr, H * 0.4); });
    g.fillStyle = '#9fd2e0'; g.font = (10 * dpr) + 'px system-ui'; g.textBaseline = 'top';
    beats.forEach(function (b, i) {
      var bx = Math.round(x(b.t));
      g.fillRect(bx - dpr, 0, 2 * dpr, H);
      g.fillText(String(i + 1) + (b.label ? ' ' + b.label : ''), bx + 3 * dpr, 0);
    });
    g.fillStyle = '#ffb454';
    var px = Math.round(x(st.t));
    g.fillRect(px - dpr, 0, 2 * dpr, H);
    g.beginPath(); g.moveTo(px - 5 * dpr, H); g.lineTo(px + 5 * dpr, H); g.lineTo(px, H - 7 * dpr); g.fill();
  }
  function tAtEvent(ev) { var r = time.getBoundingClientRect(); return (ev.clientX - r.left) / r.width * dur; }
  var dragging = false;
  time.addEventListener('pointerdown', function (ev) { dragging = true; time.setPointerCapture(ev.pointerId); play(false); show(tAtEvent(ev)); });
  time.addEventListener('pointermove', function (ev) { if (dragging) show(tAtEvent(ev)); });
  time.addEventListener('pointerup', function () { dragging = false; save(); });

  // -- grid & pointer coordinates ---------------------------------------------------
  var cams = [].slice.call(document.querySelectorAll('.lmr-anim .anim-cam'));
  var cam = cams[cams.length - 1], NS = 'http://www.w3.org/2000/svg', gridG = null;
  function drawGrid() {
    if (gridG) { gridG.remove(); gridG = null; }
    if (!st.grid || !cam) return;
    gridG = document.createElementNS(NS, 'g');
    var fh = player.fh0, fw = fh * player.asp, s = '';
    for (var gx = Math.ceil(-fw / 2); gx <= fw / 2; gx++) {
      s += '<line x1="' + gx + '" y1="' + (-fh / 2) + '" x2="' + gx + '" y2="' + (fh / 2) + '" stroke="' +
           (gx ? '#7aa7c4' : '#e06c4c') + '" stroke-opacity="' + (gx ? 0.35 : 0.8) + '" stroke-width="0.012"/>';
      if (gx) s += '<text x="' + (gx + 0.05) + '" y="-0.05" transform="scale(1,-1)" font-size="0.22" fill="#5a86a3">' + gx + '</text>';
    }
    for (var gy = Math.ceil(-fh / 2); gy <= fh / 2; gy++) {
      s += '<line x1="' + (-fw / 2) + '" y1="' + gy + '" x2="' + (fw / 2) + '" y2="' + gy + '" stroke="' +
           (gy ? '#7aa7c4' : '#e06c4c') + '" stroke-opacity="' + (gy ? 0.35 : 0.8) + '" stroke-width="0.012"/>';
      if (gy) s += '<text x="0.05" y="' + (-gy - 0.05) + '" transform="scale(1,-1)" font-size="0.22" fill="#5a86a3">' + gy + '</text>';
    }
    gridG.innerHTML = s;
    cam.appendChild(gridG);
  }
  document.addEventListener('pointermove', function (ev) {
    if (!cam) return;
    var m = cam.getScreenCTM();
    if (m && ev.clientY < window.innerHeight - bar.offsetHeight) {
      var p = new DOMPoint(ev.clientX, ev.clientY).matrixTransform(m.inverse());
      coord.textContent = 'x ' + p.x.toFixed(2) + '  y ' + p.y.toFixed(2);
    }
    inspect(ev);
  });

  // -- inspector: shapes → lines of code ---------------------------------------------
  var nodes = {}; (V.nodes || []).forEach(function (n) { nodes[n.i] = n; });
  function short(src) { return src ? src[0].split('/').pop() + ':' + src[1] : '(made inside lemur)'; }
  function openSrc(src) {
    if (!src) return;
    fetch('/__lemur/open?file=' + encodeURIComponent(src[0]) + '&line=' + src[1]).then(function (r) { return r.text(); })
      .then(function (msg) {
        if (!V.editor) {
          try { navigator.clipboard.writeText(msg); } catch (e) { /* */ }
          flash(msg + ' (copied — set --editor to open it)', 2600);
        } else flash('→ ' + short(src), 1200);
      });
  }
  function box(els) {
    var l = Infinity, t = Infinity, r = -Infinity, b = -Infinity;
    els.forEach(function (e) {
      if (e.style.display === 'none') return;
      var q = e.getBoundingClientRect();
      if (!q.width && !q.height) return;
      l = Math.min(l, q.left); t = Math.min(t, q.top); r = Math.max(r, q.right); b = Math.max(b, q.bottom);
    });
    if (!isFinite(l)) { hl.style.display = 'none'; return; }
    hl.style.display = 'block';
    hl.style.left = (l - 3) + 'px'; hl.style.top = (t - 3) + 'px';
    hl.style.width = (r - l + 6) + 'px'; hl.style.height = (b - t + 6) + 'px';
  }
  var hot = null;
  function inspect(ev) {
    if (ev.target.closest && ev.target.closest('#av-bar, #av-panel, #av-help')) { tip.style.display = 'none'; return; }
    var e = document.elementFromPoint(ev.clientX, ev.clientY), n = e && e.closest && e.closest('.lmr-anim [data-i]');
    hot = n ? nodes[+n.getAttribute('data-i')] : null;
    if (!hot) { tip.style.display = 'none'; if (!panelHot) hl.style.display = 'none'; return; }
    box([n]);
    tip.textContent = '#' + hot.i + ' ' + (hot.wk || hot.k) + ' · ' + short(hot.src);
    tip.style.display = 'block';
    tip.style.left = (ev.clientX + 14) + 'px'; tip.style.top = (ev.clientY + 12) + 'px';
  }
  window.addEventListener('click', function (ev) {
    if (ev.target.closest && ev.target.closest('#av-bar, #av-panel, #av-help')) return;
    ev.stopPropagation(); ev.preventDefault();
    if (hot) openSrc(hot.src);
  }, true);
  window.addEventListener('wheel', function (ev) {
    if (ev.target.closest && ev.target.closest('#av-panel')) return;
    ev.stopPropagation(); ev.preventDefault();
    play(false); show(st.t + (ev.deltaY > 0 ? 1 : -1) * FRAME * (ev.shiftKey ? 10 : 1)); save();
  }, { capture: true, passive: false });

  // -- panels ------------------------------------------------------------------------
  var panelHot = false;
  function renderPanel() {
    document.documentElement.style.setProperty('--av-panel', st.panel ? '340px' : '0px');
    panel.classList.toggle('open', !!st.panel);
    if (!st.panel) return;
    if (st.panel === 'log') {
      panel.innerHTML = '<h3>warnings</h3><pre>' + esc((V.warnings || []).join('\n') || '—') + '</pre>' +
                        '<h3>printed by the module</h3><pre>' + esc(V.log || '—') + '</pre>';
      return;
    }
    var groups = {}, order = [];                          // one row per line of code
    (V.nodes || []).forEach(function (n) {
      var k = n.src ? n.src.join(':') : '';
      if (!(k in groups)) { groups[k] = { src: n.src, ids: [] }; order.push(k); }
      groups[k].ids.push(n.i);
    });
    order.sort(function (a, b) {
      var A = groups[a].src, B = groups[b].src;
      if (!A || !B) return A ? -1 : 1;
      return A[0] === B[0] ? A[1] - B[1] : (A[0] < B[0] ? -1 : 1);
    });
    panel.innerHTML = '<h3>shapes, by the line that made them</h3>';
    order.forEach(function (k) {
      var g = groups[k], it = el('div', { 'class': 'av-item' },
        '<span class="av-src">' + esc(short(g.src)) + '</span><span class="av-meta">' + g.ids.length +
        (g.ids.length > 1 ? ' shapes' : ' shape') + '</span>');
      it.addEventListener('mouseenter', function () {
        panelHot = true;
        box(g.ids.map(function (i) { return document.querySelector('.lmr-anim [data-i="' + i + '"]'); }).filter(Boolean));
      });
      it.addEventListener('mouseleave', function () { panelHot = false; hl.style.display = 'none'; });
      it.addEventListener('click', function () { openSrc(g.src); });
      panel.appendChild(it);
    });
  }
  function esc(s) { return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;'); }
  function togglePanel(name) { st.panel = st.panel === name ? null : name; renderPanel(); refresh(); save(); setTimeout(function () { show(st.t); }, 60); }

  // -- buttons & keys ------------------------------------------------------------------
  function refresh() {
    bPlay.textContent = st.playing ? '❚❚' : '▶';
    bLoop.classList.toggle('on', st.loop);
    bSpeed.textContent = SPEEDS[st.speed] + '×';
    bGrid.classList.toggle('on', st.grid);
    bVec.classList.toggle('on', st.vector);
    bShapes.classList.toggle('on', st.panel === 'shapes');
    bLog.classList.toggle('on', st.panel === 'log');
  }
  bPlay.onclick = function () { play(); };
  bLoop.onclick = function () { st.loop = !st.loop; refresh(); drawTime(); save(); };
  bSpeed.onclick = function () { st.speed = (st.speed + 1) % SPEEDS.length; refresh(); save(); };
  bGrid.onclick = function () { st.grid = !st.grid; drawGrid(); refresh(); save(); };
  bVec.onclick = function () { st.vector = !st.vector; show(st.t); refresh(); save(); };
  bShapes.onclick = function () { togglePanel('shapes'); };
  bLog.onclick = function () { togglePanel('log'); };
  warn.onclick = function () { togglePanel('log'); };
  bHelp.onclick = function () { help.classList.toggle('open'); };
  window.addEventListener('keydown', function (ev) {
    if (ev.ctrlKey || ev.metaKey || ev.altKey) return;
    var k = ev.key, done = true;
    if (k === ' ') play();
    else if (k === 'ArrowRight') { play(false); ev.shiftKey ? stepBeat(1) : show(st.t + FRAME); }
    else if (k === 'ArrowLeft') { play(false); ev.shiftKey ? stepBeat(-1) : show(st.t - FRAME); }
    else if (k === 'Home') { play(false); show(0); }
    else if (k === 'End') { play(false); show(dur); }
    else if (k === 'l' || k === 'L') bLoop.onclick();
    else if (k === '[') { st.speed = Math.max(0, st.speed - 1); refresh(); }
    else if (k === ']') { st.speed = Math.min(SPEEDS.length - 1, st.speed + 1); refresh(); }
    else if (k === 'g' || k === 'G') bGrid.onclick();
    else if ((k === 'v' || k === 'V') && V.gpu) bVec.onclick();
    else if (k === 's' || k === 'S') togglePanel('shapes');
    else if (k === 'p' || k === 'P') togglePanel('log');
    else if (k === '?') help.classList.toggle('open');
    else if (k === 'Escape') help.classList.remove('open');
    else if (k === 'ArrowUp' || k === 'ArrowDown' || k === 'PageUp' || k === 'PageDown' || k === 'o' || k === 'O') { /* the deck's: swallow */ }
    else done = false;
    if (done) { ev.preventDefault(); ev.stopImmediatePropagation(); save(); }
  }, true);

  // -- rebuilds ----------------------------------------------------------------------
  try {
    var es = new EventSource('/__lemur/events');
    es.addEventListener('building', function () { flash('rebuilding…'); });
    es.addEventListener('reload', function () { save(); location.reload(); });
  } catch (e) { /* */ }
  window.addEventListener('resize', function () { drawTime(); });
  window.addEventListener('beforeunload', save);

  renderPanel(); refresh(); drawGrid();
  // after the deck's own first frame, go to where we were
  setTimeout(function () { show(st.t); }, 80);
  if (V.warnings && V.warnings.length) flash(V.warnings.length + ' warning(s) — press P', 2400);
})();
