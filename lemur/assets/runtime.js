/* runtime.js — the lemur presentation runtime. Hand-written vanilla JS, no
 * framework, no build step (ships as one self-contained file so a deck works
 * even over file://, where native ES modules are blocked).
 *
 * This is behavior only: the slide DOM is rendered at build time (lemur.html,
 * Plan-DisplayModel.md Phase 3) and present at load — the runtime never builds
 * it. A lean core plus plugins, cleanly separated:
 *   - a source-AGNOSTIC presenter CORE: the pure step/scale/hash functions and
 *     the Deck (state, navigation, scaling, transitions, the step model, hash).
 *     It knows only the *display contract* plus its extension surface: lifecycle
 *     hooks (deck.on/emit: 'show', 'step', 'layout', 'start', 'beforeFreeze',
 *     'ready') and extension points (addStepCounter, addKeyHandler, whenReady;
 *     the viewportInset / wheelNav levers). No lemur, no overview, no print.
 *   - source-agnostic PLUGINS attached through that surface: createOverview and
 *     createPrint (frozen-projection features that were once baked into Deck).
 *   - the lemur BRIDGE (attachLemur): the source-specific behaviour (code
 *     highlighting, annotation arrows, MathJax). A deck from a different source
 *     ships its own bridge and reuses the same core + feature plugins.
 *
 * The two live in one file only for single-file delivery; the boundary is the
 * hook API and is enforced by tests (tests/js/unit/presenter.test.mjs). Splitting
 * into physical ES modules needs a bundler (file:// blocks native imports) —
 * deferred to its own step.
 *
 * Usable two ways:
 *   - in the browser as <script defer src="runtime.js">, auto-initing against
 *     the first .deck once the DOM + MathJax have loaded;
 *   - in Node (node:test / jsdom) via require('runtime.js') for the API.
 */
(function (root, factory) {
  "use strict";
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  if (root) root.LMR = api;
  // Browser auto-init: defer guarantees the DOM is parsed and the MathJax
  // script (also deferred, earlier in document order) has begun startup.
  if (typeof document !== "undefined" && document.querySelector) {
    const deckEl = document.querySelector(".deck");
    if (deckEl) api.init(deckEl);
  }
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  const SVGNS = "http://www.w3.org/2000/svg";
  // annotation label geometry, in design pixels (1920x1080 design box). The
  // emitter reserves the annotations container height from the same numbers
  // (keep in sync). ARROW_STANDOFF is the gap the arrowhead keeps from glyphs.
  const ANN_TOP_PAD = 21, ANN_ROW_HEIGHT = 60, ANN_PAD = 12, ARROW_STANDOFF = 9;

  // =========================================================================
  // pure functions (Plan.md Section 5) — no side effects beyond class toggles
  // =========================================================================

  /** Uniform scale that fits a W×H design box into a vw×vh viewport
   *  (Plan.md Section 4.2). Guards a degenerate design box rather than
   *  returning Infinity/NaN. */
  function computeScale(vw, vh, W, H) {
    if (!(W > 0) || !(H > 0)) return 1;
    return Math.min(vw / W, vh / H);
  }

  /** Highest activation index used on a slide; 0 if it has none. This is S,
   *  the slide's last step (Plan.md Section 4.3). */
  function slideStepCount(slide) {
    let max = 0;
    for (const el of slide.querySelectorAll("[data-appear],[data-hl]")) {
      max = Math.max(max, Number(el.dataset.appear || 0), Number(el.dataset.hl || 0));
    }
    // overlay specs (data-when="2-4"): the largest number referenced
    for (const el of slide.querySelectorAll("[data-when]")) {
      for (const num of el.getAttribute("data-when").match(/\d+/g) || []) {
        max = Math.max(max, Number(num));
      }
    }
    return max;
  }

  /** True if step s falls in an overlay spec: a comma-separated list of terms,
   *  each 'n' (only n), 'n-' (from n), '-n' (up to n) or 'n-m' (n..m). This is
   *  the general "when to show" predicate — beamer's <n>, <n->, <-n>, <n-m>. */
  function stepInSpec(spec, s) {
    for (const term of String(spec).split(",")) {
      const m = /^\s*(\d*)(-?)(\d*)\s*$/.exec(term);
      if (!m || (m[1] === "" && m[3] === "" && m[2] === "")) continue;
      if (!m[2]) {                       // "n" — only this step
        if (m[1] !== "" && Number(m[1]) === s) return true;
      } else {                           // range: lo-hi (either side open)
        const lo = m[1] === "" ? -Infinity : Number(m[1]);
        const hi = m[3] === "" ? Infinity : Number(m[3]);
        if (s >= lo && s <= hi) return true;
      }
    }
    return false;
  }

  function codeHlMap(code) {
    // parse (and cache) the step->lines map; re-parsed on clones (freezeStage)
    if (!code._lmrHl) {
      try { code._lmrHl = JSON.parse(code.dataset.highlights); }
      catch (e) { code._lmrHl = {}; }
    }
    return code._lmrHl;
  }

  /** Highlight a code block's active line-group at step s: the group is the one
   *  with the largest step <= s (the "current group", not cumulative); its
   *  lines are emphasised and the rest dimmed. No active group => plain. */
  function applyCodeHighlight(code, s) {
    const map = codeHlMap(code);
    let active = null, best = -1;
    for (const k in map) {
      const kn = Number(k);
      if (kn <= s && kn > best) { best = kn; active = map[k]; }
    }
    for (const ln of code.querySelectorAll(".cl")) {
      const num = ln.getAttribute("data-line");
      if (active === null) ln.classList.remove("cl-hl", "cl-dim");
      else if (active.includes(num)) { ln.classList.add("cl-hl"); ln.classList.remove("cl-dim"); }
      else { ln.classList.add("cl-dim"); ln.classList.remove("cl-hl"); }
    }
  }

  /** Apply step s to a slide root: data-appear controls (cumulative) visibility,
   *  data-when is the general overlay predicate, data-hl the (cumulative)
   *  highlight. This is the source-agnostic step protocol — any bridge emits
   *  these attributes; extensions layer richer per-step behaviour via the deck's
   *  'step' hook. Shared verbatim with the print emission (Plan.md 4.3/4.7). */
  function applyStep(slide, s) {
    for (const el of slide.querySelectorAll("[data-appear]")) {
      el.classList.toggle("is-visible", Number(el.dataset.appear) <= s);
    }
    for (const el of slide.querySelectorAll("[data-hl]")) {
      el.classList.toggle("is-hl", Number(el.dataset.hl) <= s);
    }
    // overlay specs: visible only while s matches the spec (may hide again)
    for (const el of slide.querySelectorAll("[data-when]")) {
      el.classList.toggle("is-visible", stepInSpec(el.getAttribute("data-when"), s));
    }
    slide.dataset.step = String(s);
  }

  /** The frozen page DOM for step k: a clone of a fully-rendered stage with the
   *  very same applyStep applied. This is the single source of truth shared
   *  with the on-screen build, so the printed page for step k is, by
   *  construction, the stage after applyStep(k) (Plan.md Section 4.7). */
  function freezeStage(stage, k) {
    const clone = stage.cloneNode(true);
    applyStep(clone, k);
    return clone;
  }

  /** Convert a post-transform DOMRect into stage-local design coordinates: the
   *  stage is scaled, so getBoundingClientRect returns scaled pixels; subtract
   *  the stage origin and divide by the scale (Plan.md Section 4.5). */
  function toDesignCoords(rect, stageRect, scale) {
    return {
      x: (rect.left - stageRect.left) / scale,
      y: (rect.top - stageRect.top) / scale,
      w: rect.width / scale,
      h: rect.height / scale
    };
  }

  /** Compute a cubic-bezier arrow from a callout box to a target box, both in
   *  design coordinates (Plan.md Section 4.5). The line leaves the callout edge
   *  nearest the target's horizontal centre and ends a small standoff gap short
   *  of the target so the arrowhead does not overlap the glyphs. Returns the
   *  two endpoints and two control points; a near-vertical S-curve. */
  function arrowEndpoints(callout, target, opts = {}) {
    const standoff = opts.standoff != null ? opts.standoff : 6;
    const tcx = target.x + target.w / 2;               // target centre x
    const x0 = Math.max(callout.x + 4,
      Math.min(tcx, callout.x + callout.w - 4));        // start on callout edge
    const below = (callout.y + callout.h / 2) >= (target.y + target.h / 2);
    const x1 = tcx;
    let y0, y1;
    if (below) {                       // callout under the target: point up
      y0 = callout.y;
      y1 = target.y + target.h + standoff;
    } else {                           // callout above the target: point down
      y0 = callout.y + callout.h;
      y1 = target.y - standoff;
    }
    const my = (y0 + y1) / 2;          // control points pull the curve vertical
    return { x0, y0, x1, y1, c1x: x0, c1y: my, c2x: x1, c2y: my };
  }

  /** Compute a cubic-bezier connector between two arbitrary boxes (design
   *  coords) — the mark-to-mark case (`!connect`). Attaches on the facing edges
   *  along the dominant axis (left/right when mostly horizontal, top/bottom when
   *  mostly vertical) and bows the curve perpendicular to that axis, so a
   *  same-line question->answer reads as a sideways arc and a stacked pair as a
   *  vertical one. `to` gets a standoff gap for the arrowhead. */
  function connectEndpoints(from, to, opts = {}) {
    const standoff = opts.standoff != null ? opts.standoff : 6;
    const fcx = from.x + from.w / 2, fcy = from.y + from.h / 2;
    const tcx = to.x + to.w / 2, tcy = to.y + to.h / 2;
    // pick the axis from how the boxes overlap: sharing a line (vertical
    // overlap, no horizontal) reads best as a sideways arrow; stacked (they
    // share a column) as a vertical one; otherwise the dominant centre axis.
    const overlapX = Math.min(from.x + from.w, to.x + to.w) - Math.max(from.x, to.x);
    const overlapY = Math.min(from.y + from.h, to.y + to.h) - Math.max(from.y, to.y);
    const horizontal = overlapY > 0 && overlapX <= 0 ? true
      : overlapX > 0 && overlapY <= 0 ? false
        : Math.abs(tcx - fcx) >= Math.abs(tcy - fcy);
    let x0, y0, x1, y1, c1x, c1y, c2x, c2y;
    if (horizontal) {                                   // horizontal-dominant
      y0 = fcy; y1 = tcy;
      if (tcx >= fcx) { x0 = from.x + from.w; x1 = to.x - standoff; }
      else { x0 = from.x; x1 = to.x + to.w + standoff; }
      const mx = (x0 + x1) / 2;         // pull control points horizontal
      c1x = mx; c1y = y0; c2x = mx; c2y = y1;
    } else {                            // vertical-dominant
      x0 = fcx; x1 = tcx;
      if (tcy >= fcy) { y0 = from.y + from.h; y1 = to.y - standoff; }
      else { y0 = from.y; y1 = to.y + to.h + standoff; }
      const my = (y0 + y1) / 2;         // pull control points vertical
      c1x = x0; c1y = my; c2x = x1; c2y = my;
    }
    return { x0, y0, x1, y1, c1x, c1y, c2x, c2y };
  }

  /** Build one `<g class="arrow">` (a cubic-bezier path with arrowheads per
   *  `dir`) from precomputed endpoints and append it to the arrow layer. Shared
   *  by annotation callouts (dir "fwd") and `!connect` links (any dir). Styles
   *  (dashed/thin/…) become `arrow-<style>` classes; the single arrowhead marker
   *  is `orient=auto-start-reverse`, so it serves both ends. */
  function drawArrow(svg, ep, opts = {}) {
    const g = document.createElementNS(SVGNS, "g");
    let cls = "arrow";
    for (const st of opts.styles || []) if (st) cls += ` arrow-${st}`;
    g.setAttribute("class", cls);
    if (opts.appear != null) g.setAttribute("data-appear", String(opts.appear));
    if (opts.to) g.setAttribute("data-to", opts.to);   // for debugging/tests
    if (opts.color) g.style.setProperty("--arrow-color", opts.color.trim());
    const path = document.createElementNS(SVGNS, "path");
    path.setAttribute("class", "arrow-line");
    path.setAttribute("d",
      `M ${ep.x0} ${ep.y0} C ${ep.c1x} ${ep.c1y}, ${ep.c2x} ${ep.c2y}, ${ep.x1} ${ep.y1}`);
    const dir = opts.dir || "fwd";
    if (dir === "fwd" || dir === "both") path.setAttribute("marker-end", "url(#lmr-arrowhead)");
    if (dir === "back" || dir === "both") path.setAttribute("marker-start", "url(#lmr-arrowhead)");
    g.appendChild(path);
    svg.appendChild(g);
    try { path.style.setProperty("--arrow-len", path.getTotalLength()); }
    catch (e) { /* getTotalLength unsupported (jsdom): skip the draw-on */ }
    return g;
  }

  /** Parse a '#/<slide>/<step>' location hash. Tolerant: a missing step is 0,
   *  and anything unparseable returns null (the caller falls back to 0,0). */
  function parseHash(hash) {
    const m = /\/(\d+)(?:\/(\d+))?/.exec(hash || "");
    return m ? { slide: Number(m[1]), step: m[2] != null ? Number(m[2]) : 0 } : null;
  }

  /** Format a location as '#/<slide>/<step>'. */
  function formatHash(slideIndex, step) {
    return `#/${slideIndex}/${step}`;
  }

  /** Clamp an arbitrary (slideIndex, step) to a valid location. `deck` is
   *  {steps: [S0, S1, ...]} so this is testable without a DOM (Plan.md 5,
   *  Section 11 "hash out of range"). */
  function clampLocation(slideIndex, step, deck) {
    const steps = (deck && deck.steps) || [];
    const n = steps.length;
    if (n === 0) return { slide: 0, step: 0 };
    let si = Number(slideIndex);
    if (!(si >= 0)) si = 0;
    if (si > n - 1) si = n - 1;
    let st = Number(step);
    if (!(st >= 0)) st = 0;
    if (st > steps[si]) st = steps[si];
    return { slide: si, step: st };
  }

  // =========================================================================
  // imperative shell — the Deck (integration-tested in the browser)
  // =========================================================================

  class Deck {
    #hooks = {};                 // event name -> [fn]; the extension surface
    #stepCounters = [];          // fn(slide) -> extra step count (extensions)
    #keyHandlers = [];           // fn(e) -> handled?; plugins claim keys first
    #ready = [];                 // promises awaited before the 'ready' hook
    #shown = null;               // last slide index shown (jump detection)
    #progress = null;            // the progress-bar element, if the deck opts in
    #abort = null;               // AbortController grouping the window listeners
    #resizeObs = null;           // ResizeObserver for viewport/layout changes
    #wheelAt = 0;                // last wheel-nav timestamp (throttles the wheel)

    constructor(el) {
      this.el = el;
      this.slides = [...el.querySelectorAll(":scope > .slide")];
      this.W = Number(el.dataset.designW) || 1280;
      this.H = Number(el.dataset.designH) || 720;
      this.steps = this.slides.map(slideStepCount);
      this.i = 0;
      this.s = 0;
      this.scale = 1;
      // plugin-tunable presenter state (a docked panel sets viewportInset so the
      // scale fits what's left; an overlay clears wheelNav to suspend wheel-nav)
      this.viewportInset = 0;
      this.wheelNav = true;
      this.signal = null;        // the window-listener AbortController's signal
      this.nav = typeof document !== "undefined"
        ? document.querySelector(".deck-nav") : null;
    }

    location() { return { slide: this.i, step: this.s }; }

    // -- extension surface: lifecycle hooks the presenter fires and any bridge
    //    or decorator subscribes to. Source-specific behaviour (lemur arrows,
    //    code highlighting, math) lives entirely in these subscribers, never in
    //    the core. Events: 'show'(i), 'step'(root, s), 'layout'(),
    //    'beforeFreeze'(), 'ready'().

    /** Subscribe `fn` to a lifecycle event. Returns the deck for chaining. */
    on(name, fn) { (this.#hooks[name] ??= []).push(fn); return this; }

    /** Fire an event to its subscribers with the given arguments. */
    emit(name, ...args) { for (const fn of this.#hooks[name] ?? []) fn(...args); }

    /** An extension contributes extra steps to a slide (e.g. code highlights). */
    addStepCounter(fn) { this.#stepCounters.push(fn); }

    /** A plugin claims keys: `fn(e)` runs before the core's own nav keys and
     *  returns true if it handled the event (the core then preventDefaults and
     *  stops). Lets features like the overview own their keys without the core
     *  knowing them. */
    addKeyHandler(fn) { this.#keyHandlers.push(fn); }

    /** An extension registers a promise the deck awaits before firing 'ready'. */
    whenReady(promise) { if (promise) this.#ready.push(promise); }

    /** The step count of a slide: the core protocol plus every extension's. */
    countSteps(slide) {
      let max = slideStepCount(slide);
      for (const counter of this.#stepCounters) max = Math.max(max, counter(slide));
      return max;
    }

    /** Recompute every slide's step count (after an extension changes the DOM). */
    recountSteps() { this.steps = this.slides.map((sl) => this.countSteps(sl)); }

    /** Apply the full step state to a root: the core protocol, then the 'step'
     *  hook so extensions layer their per-step DOM (used on-screen and on the
     *  cloned print pages, so both stay identical). */
    applyState(root, s) { applyStep(root, s); this.emit("step", root, s); }

    /** Boot the deck (after any extensions have attached): count steps, scale,
     *  create the progress bar, honour the incoming hash, then wire input /
     *  resize / print and await the extensions' readiness (e.g. math) before
     *  firing 'ready'. Source-agnostic; listeners share one AbortController. */
    start() {
      this.recountSteps();               // include the extensions' step counters
      this.resize();
      this.#createProgress();
      this.fromHash();
      this.syncHash(false);              // normalise the URL to the clamped location
      const { signal } = (this.#abort = new AbortController());
      this.signal = signal;              // plugins scope their listeners to it
      // nav wedges: click to step; blur so a focused button does not also fire
      // on the next Space/Enter (the window keydown handler covers that)
      if (this.nav) {
        const prev = this.nav.querySelector(".deck-nav-prev");
        const next = this.nav.querySelector(".deck-nav-next");
        prev?.addEventListener("click", () => { this.prev(); prev.blur(); }, { signal });
        next?.addEventListener("click", () => { this.next(); next.blur(); }, { signal });
      }
      window.addEventListener("keydown", (e) => this.onKey(e), { signal });
      window.addEventListener("wheel", (e) => this.onWheel(e),
        { signal, passive: false });
      window.addEventListener("hashchange", () => this.fromHash(), { signal });
      // a ResizeObserver on the viewport is more robust than the resize event
      // (it also catches layout changes); fall back where it is unsupported.
      // Extensions re-measure layout-dependent things (arrows, thumbs) on 'layout'.
      const onLayout = () => { this.resize(); this.emit("layout"); };
      if (typeof ResizeObserver !== "undefined") {
        this.#resizeObs = new ResizeObserver(onLayout);
        this.#resizeObs.observe(document.documentElement);
      } else {
        window.addEventListener("resize", onLayout, { signal });
      }
      this.emit("start");                // plugins wire signal-scoped listeners
      // once the extensions' readiness (math) and fonts settle, layout metrics are
      // final: let extensions finalise (arrows, coloring), then check overflow
      const fontsReady = (typeof document !== "undefined" && document.fonts &&
        document.fonts.ready) || null;
      Promise.all([...this.#ready, fontsReady].filter(Boolean)).then(() => {
        this.emit("ready");
        this.checkOverflow();
      });
    }

    /** Recompute and apply the uniform scale for the current viewport. Arrows do
     *  not need re-measuring for a pure scale change (endpoints are cached in
     *  design space); layout-affecting changes are handled separately. */
    resize() {
      // a docked panel (e.g. the overview sidebar) reserves viewportInset px, so
      // scale to fit what is left and the live slide stays fully visible beside it
      const vw = Math.max(1, window.innerWidth - this.viewportInset);
      const s = computeScale(vw, window.innerHeight, this.W, this.H);
      this.el.style.setProperty("--scale", String(s));
      this.scale = s;
    }

    /** Park every slide by its position relative to the current one: the current
     *  slide is centred (is-current), earlier slides rest off to the left
     *  (is-before), later ones off to the right (is-after). The one slide we are
     *  leaving is also flagged is-out: it stays shown while it slides away and is
     *  the background the incoming slide crossfades over (push). Only the current
     *  and outgoing slides are shown, so no third slide's opaque background
     *  occludes the crossfade. A slide's resting place is a pure function of its
     *  index, so going forward and back are the same toggle in reverse — no
     *  direction flag, no cleanup timer (cf. the within-slide step model). Only
     *  'slide'/'push' read these classes; 'fade'/'none' ignore them. A jump of
     *  more than one slide is cut (.no-anim + one reflow) so the slides in
     *  between do not sweep across the frame. */
    showSlide(i) {
      const prev = this.#shown;
      const jump = prev != null && Math.abs(i - prev) > 1;
      if (jump) this.el.classList.add("no-anim");
      for (let k = 0; k < this.slides.length; k++) {
        const d = k - i, cl = this.slides[k].classList;
        cl.toggle("is-current", d === 0);
        cl.toggle("is-before", d < 0);
        cl.toggle("is-after", d > 0);
        cl.toggle("is-out", prev !== i && k === prev);
      }
      if (jump) { void this.el.offsetWidth; this.el.classList.remove("no-anim"); }
      this.#shown = i;
    }

    /** Move to (i, s), clamped, and update the DOM, hash, and extensions. */
    go(i, s, viaHash) {
      const loc = clampLocation(i, s, this);
      const slideChanged = loc.slide !== this.i;
      this.i = loc.slide;
      this.s = loc.step;
      this.showSlide(this.i);
      this.emit("show", this.i);              // extensions: e.g. measure arrows
      // Entering a different slide snaps its step state instead of animating it:
      // the step transitions (fade/rise reveals, highlight colour) are for
      // within-slide stepping only. A slide may carry stale reveals from an
      // earlier visit (e.g. jumping back via the overview) or reveal its last
      // step when stepped into backwards; either must cut, not fade, or those
      // elements flash as they animate out/in. One reflow with the step
      // transitions off commits the target state, mirroring showSlide's own
      // no-anim cut of the slide transform for multi-slide jumps.
      if (slideChanged) this.el.classList.add("no-step-anim");
      this.applyState(this.slides[this.i], this.s);
      if (slideChanged) {
        void this.el.offsetWidth;
        this.el.classList.remove("no-step-anim");
      }
      this.updateNav();
      this.#updateProgress();
      if (!viaHash) this.syncHash(slideChanged);
    }

    /** Reflect the location in the nav wedges: dim them at the very ends, and
     *  cue Next when it uncovers more on this slide vs moves to the next one. */
    updateNav() {
      if (!this.nav) return;
      const atStart = this.i === 0 && this.s === 0;
      const atEnd = this.i === this.slides.length - 1 && this.s === this.steps[this.i];
      this.nav.classList.toggle("at-start", atStart);
      this.nav.classList.toggle("at-end", atEnd);
      this.nav.dataset.more = this.s < this.steps[this.i] ? "step" : "slide";
    }

    // -- progress bar (presenter UI): created only when the deck opts in via
    //    data-progress; its scaleX tracks the deck's position across all the
    //    (slide, step) stops. Off entirely otherwise.
    #createProgress() {
      const pos = this.el.dataset.progress;
      if (!pos) return;
      const bar = document.createElement("div");
      bar.className = "deck-progress";
      bar.setAttribute("data-pos", pos);
      bar.setAttribute("aria-hidden", "true");
      this.el.appendChild(bar);
      this.#progress = bar;
      this.#updateProgress();
    }

    #updateProgress() {
      if (!this.#progress) return;
      let done = 0, total = 0;
      for (let k = 0; k < this.slides.length; k++) {
        const stops = this.steps[k] + 1;      // step 0 .. steps[k]
        if (k < this.i) done += stops;
        else if (k === this.i) done += this.s;
        total += stops;
      }
      this.#progress.style.transform =
        `scaleX(${total > 1 ? done / (total - 1) : 1})`;
    }

    /** Advance one step, rolling into the next slide at step 0 past S. */
    next() {
      if (this.s < this.steps[this.i]) this.go(this.i, this.s + 1);
      else if (this.i < this.slides.length - 1) this.go(this.i + 1, 0);
    }

    /** Step back, rolling into the previous slide's last step. No-op at start. */
    prev() {
      if (this.s > 0) this.go(this.i, this.s - 1);
      else if (this.i > 0) this.go(this.i - 1, this.steps[this.i - 1]);
    }

    first() { this.go(0, 0); }
    last() { const n = this.slides.length - 1; this.go(n, this.steps[n]); }

    /** Slide changes push a history entry (Back walks slides); step changes
     *  replace it, so stepping does not flood history (Plan.md 5). */
    syncHash(slideChanged) {
      const h = formatHash(this.i, this.s);
      if (("" + location.hash) === h) return;
      try {
        if (slideChanged) history.pushState(null, "", h);
        else history.replaceState(null, "", h);
      } catch (e) {
        location.hash = h;           // file:// or sandbox without History API
      }
    }

    fromHash() {
      const p = parseHash(location.hash);
      if (p) { this.go(p.slide, p.step, true); return; }
      // a named anchor (#/<id>): jump to the slide containing that element —
      // what reference/citation links use (@ref, @cite, [text]@ref)
      const id = (location.hash || "").replace(/^#\/?/, "");
      if (id) {
        const el = document.getElementById(id);
        const slide = el && el.closest && el.closest(".slide");
        const idx = slide ? this.slides.indexOf(slide) : -1;
        if (idx >= 0) {
          this.go(idx, 0, true);
          this.syncHash(false);      // normalise #/<id> to #/<slide>/0
          return;
        }
      }
      this.go(0, 0, true);
    }


    /** Flag slides whose content overflows the design box: always warn, and in
     *  dev (?dev) draw a dashed outline (content is clipped by overflow:hidden
     *  either way, so it never bleeds into a neighbour). */
    checkOverflow() {
      const dev = /(?:^|[?&])dev(?:[=&]|$)/.test(location.search);
      for (let i = 0; i < this.slides.length; i++) {
        const stage = this.slides[i].querySelector(".stage");
        const over = stage.scrollWidth > this.W + 2 ||
          stage.scrollHeight > this.H + 2;
        if (over && window.console) {
          console.warn(`lemur: slide ${i} content overflows the ` +
            `${this.W}x${this.H} design box (clipped)`);
        }
        if (dev) stage.classList.toggle("stage--overflow", over);
      }
    }

    onKey(e) {
      if (e.defaultPrevented || e.metaKey || e.ctrlKey || e.altKey) return;
      // plugins (e.g. the overview) claim keys first; a handler returning true
      // consumes the event, so the core never learns feature-specific keys
      for (const fn of this.#keyHandlers) {
        if (fn(e)) { e.preventDefault(); return; }
      }
      switch (e.key) {
        case "ArrowRight": case "ArrowDown": case "PageDown": case " ":
          this.next(); break;
        case "ArrowLeft": case "ArrowUp": case "PageUp":
          this.prev(); break;
        case "Home": this.first(); break;
        case "End": this.last(); break;
        default: return;
      }
      e.preventDefault();
    }

    /** Mouse-wheel navigation: down = forward, up = back. Throttled so one notch
     *  (or a trackpad's momentum burst) = one step. A plugin clears wheelNav to
     *  suspend it (the overview does, so its scroll stays native). Ctrl/⌘+wheel
     *  is left to browser zoom. */
    onWheel(e) {
      if (!this.wheelNav || e.ctrlKey || e.metaKey || !e.deltaY) return;
      e.preventDefault();
      const now = Date.now();
      if (now - this.#wheelAt < 100) return;
      this.#wheelAt = now;
      if (e.deltaY > 0) this.next(); else this.prev();
    }

    /** Tear down the window/observer listeners (rarely needed; enables re-init). */
    destroy() {
      this.#abort?.abort();
      this.#resizeObs?.disconnect();
    }
  }

  /** Log every MathJax render error to the console (Plan.md Section 11). The
   *  offending source is already shown in a red error box in place of the
   *  equation by MathJax; the slide is never blanked. Returns the count. */
  function logMathErrors() {
    if (typeof document === "undefined") return 0;
    const errs = document.querySelectorAll("[data-mjx-error]");
    for (const err of errs) {
      if (window.console) {
        console.error(`lemur: math error: ${err.getAttribute("data-mjx-error")}`);
      }
    }
    return errs.length;
  }

  /** Syntax-colorize code with highlight.js if it is loaded (item 6). Each
   *  line is colorized independently so the per-line spans (used for step
   *  line-highlighting) are preserved; the small trade-off is that a construct
   *  spanning lines (e.g. a multi-line string) is colored per line. Runs before
   *  print pages are cloned so the PDF is colorized too. No-op without hljs. */
  function colorizeCode() {
    if (typeof window === "undefined" || !window.hljs) return;
    for (const code of document.querySelectorAll('pre.lmr-code > code[class*="language-"]')) {
      const m = /language-([\w+.#-]+)/.exec(code.className);
      const lang = m && m[1];
      if (!lang || !window.hljs.getLanguage(lang)) continue;
      code.classList.add("hljs");
      for (const ln of code.querySelectorAll(".cl")) {
        try {
          ln.innerHTML = window.hljs.highlight(ln.textContent,
            { language: lang, ignoreIllegals: true }).value;
        } catch (e) { /* leave the line plain */ }
      }
    }
  }

  /** Typeset math (MathJax, runtime) and return a promise that resolves once
   *  the layout is final, so anything measuring math (arrows, M4) can wait for
   *  it. The deck DOM is present at load (rendered at build time), so MathJax
   *  auto-typesets it on startup; startup.promise resolves after that pass.
   *  Returns null when MathJax is absent (graceful degradation). */
  function renderMath() {
    if (typeof window === "undefined") return null;
    const MJ = window.MathJax;
    return MJ && MJ.startup && MJ.startup.promise ? MJ.startup.promise : null;
  }


  // =========================================================================
  // lemur runtime extensions — the lemur-specific behaviour (code highlighting,
  // annotation arrows, MathJax, highlight.js) lives here, wired to a
  // source-agnostic deck through its lifecycle hooks. The presenter core above
  // knows none of it; a different bridge would attach its own extensions the
  // same way. Arrows are the acid test that this boundary is real.
  // =========================================================================

  /** Extra steps a slide gets from code line-highlight groups. */
  function codeStepCount(slide) {
    let max = 0;
    for (const code of slide.querySelectorAll("[data-highlights]")) {
      for (const k in codeHlMap(code)) max = Math.max(max, Number(k));
    }
    return max;
  }

  /** The annotation/arrow decorator for a deck: places each callout under its
   *  math/prose anchor (.callout[data-anchor] -> .lmr-a-<name>) and draws a
   *  scaled bezier to it, all in design coordinates. Owns its own measured-slide
   *  cache; the presenter core holds none of this. */
  function createAnnotations(deck) {
    const measured = [];

    // the arrow overlay lives INSIDE .stage-content (not .stage): the marks it
    // targets are in .stage-content, and under the 'push' transition that is the
    // element that moves. Keeping the overlay there makes it travel with the
    // content and share one transform-invariant coordinate space with its targets.
    // Its viewBox is (re)set per measure to the measured content box (design px).
    function arrowLayer(content) {
      let svg = content.querySelector(":scope > svg.arrow-layer");
      if (!svg) {
        svg = document.createElementNS(SVGNS, "svg");
        svg.setAttribute("class", "arrow-layer");
        svg.setAttribute("preserveAspectRatio", "none");
        svg.setAttribute("aria-hidden", "true");
        content.appendChild(svg);
      }
      return svg;
    }

    /** Place + draw a slide's arrows. Returns true once targets have real boxes,
     *  false if math is not laid out yet (retried on the next 'ready'). */
    function measureArrows(i) {
      const slide = deck.slides[i];
      const callouts = slide.querySelectorAll(".callout[data-anchor]");
      const connects = slide.querySelectorAll(".lmr-connect");
      if (!callouts.length && !connects.length) return true;   // nothing to do
      // measure and draw everything in the .stage-content coordinate frame (see
      // arrowLayer): it is transform-invariant, so arrows stay locked to their
      // marks in every transition — notably 'push', which translates .stage-content
      // while .stage stays put (measuring against .stage put a push-navigated
      // slide's arrows a full design-width off; see tests/js/integration/push).
      const content = slide.querySelector(".stage-content");
      const scale = deck.scale || 1;

      for (const co of callouts) {
        co.classList.remove("is-placed");
        co.style.left = co.style.top = "";
      }
      const originRect = content.getBoundingClientRect();
      const cw = originRect.width / scale, ch = originRect.height / scale;
      if (!(cw > 0) || !(ch > 0)) return false;    // content not laid out yet
      const container = slide.querySelector(".lmr-annotations");
      const baseY = container
        ? toDesignCoords(container.getBoundingClientRect(), originRect, scale).y : 0;
      // a mark-group's boxes in design coords — a name may repeat (each
      // occurrence is one box); skip any not laid out yet (math still pending)
      const boxes = (cls) => {
        const out = [];
        for (const el of slide.querySelectorAll("." + cls)) {
          const b = toDesignCoords(el.getBoundingClientRect(), originRect, scale);
          if (b.w >= 1 || b.h >= 1) out.push(b);
        }
        return out;
      };
      const union = (bs) => {                    // bounding box over a group
        const x0 = Math.min(...bs.map((b) => b.x)), y0 = Math.min(...bs.map((b) => b.y));
        const x1 = Math.max(...bs.map((b) => b.x + b.w));
        const y1 = Math.max(...bs.map((b) => b.y + b.h));
        return { x: x0, y: y0, w: x1 - x0, h: y1 - y0 };
      };
      const nearest = (b, list) => {             // list-box closest to b's centre
        const cx = b.x + b.w / 2, cy = b.y + b.h / 2;
        let best = list[0], bd = Infinity;
        for (const o of list) {
          const dx = o.x + o.w / 2 - cx, dy = o.y + o.h / 2 - cy, d = dx * dx + dy * dy;
          if (d < bd) { bd = d; best = o; }
        }
        return best;
      };

      const svg = arrowLayer(content);
      svg.setAttribute("viewBox", `0 0 ${cw} ${ch}`);   // 1:1 with content design px
      svg.replaceChildren();

      let any = false, row = 0;
      // annotation callouts: a label in the band below; one arrow up to each of
      // its mark's occurrences (a group shares the label, colour and step)
      for (const co of callouts) {
        if (!co.textContent.trim()) continue;    // label-less: emphasis, no arrow
        const tBoxes = boxes(co.dataset.anchor);
        if (!tBoxes.length) continue;            // absent / math not laid out yet
        any = true;

        const cbox = toDesignCoords(co.getBoundingClientRect(), originRect, scale);
        const w = cbox.w, hgt = cbox.h, u = union(tBoxes);
        const x = Math.max(ANN_PAD,
          Math.min(u.x + u.w / 2 - w / 2, cw - w - ANN_PAD));
        const y = baseY + ANN_TOP_PAD + row++ * ANN_ROW_HEIGHT;
        co.classList.add("is-placed");
        co.style.left = `${x}px`;
        co.style.top = `${y}px`;

        for (const tBox of tBoxes) {
          const ep = arrowEndpoints({ x, y, w, h: hgt }, tBox, { standoff: ARROW_STANDOFF });
          drawArrow(svg, ep, { appear: co.dataset.appear, to: co.dataset.anchor,
            color: co.style.getPropertyValue("--arrow-color"), dir: "fwd" });
        }
      }
      // !connect links: arrows between two mark groups. Cover every occurrence of
      // the larger group, pairing each to its nearest counterpart (keeps the
      // from->to orientation); reduces to a single arrow for the plain 1:1 case.
      for (const c of connects) {
        const fBoxes = boxes(c.dataset.from), tBoxes = boxes(c.dataset.to);
        if (!fBoxes.length || !tBoxes.length) continue;
        any = true;
        const opts = { appear: c.dataset.appear, to: c.dataset.to, dir: c.dataset.dir,
          styles: (c.dataset.styles || "").split(/\s+/),
          color: c.style.getPropertyValue("--arrow-color") };
        const pairs = fBoxes.length >= tBoxes.length
          ? fBoxes.map((f) => [f, nearest(f, tBoxes)])
          : tBoxes.map((t) => [nearest(t, fBoxes), t]);
        for (const [f, t] of pairs)
          drawArrow(svg, connectEndpoints(f, t, { standoff: ARROW_STANDOFF }), opts);
      }
      return any;
    }

    const applyCurrent = () => deck.applyState(deck.slides[deck.i], deck.s);
    return {
      // measure a slide's arrows the first time it is shown; a pre-math attempt
      // returns false and is retried later
      ensureMeasured(i) { if (!measured.includes(i) && measureArrows(i)) measured.push(i); },
      // force a (re)measure of one slide — the current slide once math + fonts
      // settle, whose pre-math attempt failed or used stale metrics
      measure(i) { measureArrows(i); if (!measured.includes(i)) measured.push(i); applyCurrent(); },
      // draw every not-yet-drawn slide's arrows (before print, so each frozen
      // page has them); already-drawn slides are scale-invariant, so skipped
      measureAll() {
        deck.slides.forEach((_, i) => {
          if (!measured.includes(i) && measureArrows(i)) measured.push(i);
        });
        applyCurrent();
      },
      // stamp data-hl/--hl onto each callout's target anchor so the core step
      // model colours it declaratively (the parser cannot put this in the TeX —
      // MathJax builds that DOM only at runtime)
      decorate() {
        for (const slide of deck.slides) {
          for (const co of slide.querySelectorAll(".callout[data-anchor]")) {
            const col = co.style.getPropertyValue("--hl");
            const styles = co.dataset.styles;
            // a mark name may repeat (a group): colour every occurrence, together
            for (const target of slide.querySelectorAll(`.${co.dataset.anchor}`)) {
              target.dataset.hl = co.dataset.appear;
              if (col) target.style.setProperty("--hl", col.trim());
              if (styles) styles.split(/\s+/).forEach((st) => st && target.classList.add(`hl-${st}`));
            }
          }
        }
      }
    };
  }

  /** Wire the lemur extensions onto a deck's lifecycle hooks. The one place the
   *  lemur features touch the deck; a markdown/latex bridge would do the same
   *  with its own extensions. */
  function attachLemur(deck) {
    colorizeCode();                       // hljs, before math + print cloning
    deck.whenReady(renderMath());         // MathJax typeset promise

    // code line-highlighting: contributes steps, and paints per step (on-screen
    // and on the cloned print pages — both go through the 'step' hook)
    deck.addStepCounter(codeStepCount);
    deck.on("step", (root, s) => {
      for (const code of root.querySelectorAll("[data-highlights]")) applyCodeHighlight(code, s);
    });

    // annotation arrows: measured lazily when a slide is shown, and all of them
    // before any frozen projection (print pages, overview thumbnails) is built —
    // the 'beforeFreeze' hook. The current slide is (re)measured, with data-hl
    // stamped from the callouts and step counts refreshed, once math + fonts
    // settle. No 'layout' handler: endpoints are in design coords, so they scale
    // with the stage for free (a pure resize needs no re-measure).
    const ann = createAnnotations(deck);
    deck.on("show", (i) => ann.ensureMeasured(i));
    deck.on("beforeFreeze", () => ann.measureAll());
    deck.on("ready", () => {
      logMathErrors();
      ann.decorate();
      deck.recountSteps();
      ann.measure(deck.i);
    });
  }

  // =========================================================================
  // source-agnostic presenter features — print and the slide overview. Both are
  // frozen-projection features (they clone stages via freezeStage) that attach
  // to the core through the same hooks + extension points a source bridge uses;
  // the core knows neither. Split out of the Deck class so it stays a lean core.
  // =========================================================================

  /** Print plugin: build the frozen per-step pages into .print-root — one
   *  .print-page per cumulative step per slide, frozen via freezeStage then the
   *  'step' hook, so print matches the screen. Lazy (beforeprint / Ctrl-P) unless
   *  the deck opted into eager (data-print="eager" or ?print) for the zero-tooling
   *  `chrome --headless --print-to-pdf` path. Exposes deck.print.build(). */
  function createPrint(deck) {
    function build() {
      const root = document.querySelector(".print-root");
      if (!root) return 0;
      deck.emit("beforeFreeze");     // extensions: e.g. draw every arrow first
      while (root.firstChild) root.removeChild(root.firstChild);
      // the cloned stages live outside .deck, so carry the design size to them
      root.style.setProperty("--design-w", deck.W + "px");
      root.style.setProperty("--design-h", deck.H + "px");
      let pages = 0;
      for (let i = 0; i < deck.slides.length; i++) {
        const stage = deck.slides[i].querySelector(".stage");
        // the frozen page carries the slide's variant/kind classes (not 'slide'
        // or the transient is-* state), so per-slide CSS renders it faithfully
        const variants = [...deck.slides[i].classList]
          .filter((c) => c !== "slide" && !c.startsWith("is-"));
        for (let k = 0; k <= deck.steps[i]; k++) {
          const page = document.createElement("section");
          page.className = ["print-page", ...variants].join(" ");
          const clone = freezeStage(stage, k);   // core step state, then extensions
          deck.emit("step", clone, k);
          page.appendChild(clone);
          root.appendChild(page);
          pages++;
        }
      }
      return pages;
    }
    const eager = () => deck.el.dataset.print === "eager" ||
      /(?:^|[?&])print(?:[=&]|$)/.test(location.search);
    deck.on("start", () =>
      window.addEventListener("beforeprint", build, { signal: deck.signal }));
    deck.on("ready", () => { if (eager()) build(); });
    return (deck.print = { build });
  }

  /** Slide overview plugin: a grid (Slide Sorter) or a docked sidebar of
   *  thumbnails, each a frozen clone of a slide at its FINAL step. Owns its own
   *  mode + plane; attaches via a key handler (o/O/Esc + grid keys), the 'show'
   *  and 'layout' hooks, and the core's viewportInset / wheelNav levers (the
   *  docked sidebar reserves width; the open overview suspends wheel-nav so its
   *  scroll stays native). Exposes deck.overview.{mode, build, toggle, gotoSlide}. */
  function createOverview(deck) {
    let mode = "present";        // "present" | "grid" | "sidebar"
    let plane = null;            // the built .deck-overview plane (lazy, cached)

    // restore a remembered sidebar width (from a previous drag)
    try {
      const w = localStorage.getItem("lmr-sidebar-w");
      if (w) document.documentElement.style.setProperty("--sidebar-w", w + "px");
    } catch (e) { /* file:// or a sandbox without localStorage */ }

    function build() {
      if (plane) return plane;
      deck.emit("beforeFreeze");     // extensions: draw every slide's arrows first
      plane = document.createElement("div");
      plane.className = "deck-overview";
      plane.hidden = true;
      plane.setAttribute("aria-label", "Slide overview");
      plane.style.setProperty("--design-w", deck.W + "px");
      plane.style.setProperty("--design-h", deck.H + "px");
      plane.style.setProperty("--aspect", String(deck.W / deck.H));
      const grid = document.createElement("div");
      grid.className = "deck-overview-grid";
      for (let i = 0; i < deck.slides.length; i++) {
        const stage = deck.slides[i].querySelector(".stage");
        const variants = [...deck.slides[i].classList]
          .filter((c) => c !== "slide" && !c.startsWith("is-"));
        const clone = freezeStage(stage, deck.steps[i]);   // the final variant
        deck.emit("step", clone, deck.steps[i]);           // extensions per step
        const title = (deck.slides[i].querySelector("h1, h2") || {}).textContent || "";
        const thumb = document.createElement("button");
        thumb.type = "button";
        thumb.className = ["overview-thumb", ...variants].join(" ");
        thumb.dataset.slide = String(i);
        thumb.setAttribute("aria-label", `Slide ${i + 1}${title ? ": " + title : ""}`);
        const box = document.createElement("div");
        box.className = "overview-thumb-stage";
        box.appendChild(clone);
        const cap = document.createElement("div");
        cap.className = "overview-thumb-cap";
        cap.textContent = `${i + 1}${title ? " · " + title : ""}`;
        thumb.append(box, cap);
        thumb.addEventListener("click", () => gotoSlide(i));
        grid.appendChild(thumb);
      }
      plane.appendChild(grid);
      const resizer = document.createElement("div");   // drag the sidebar wider
      resizer.className = "deck-overview-resizer";
      resizer.setAttribute("aria-hidden", "true");
      plane.appendChild(resizer);
      wireResizer(resizer);
      document.body.appendChild(plane);
      return plane;
    }

    function wireResizer(resizer) {
      const setWidth = (px) => {
        const w = Math.max(160, Math.min(px, window.innerWidth * 0.6));
        document.documentElement.style.setProperty("--sidebar-w", w + "px");
        deck.viewportInset = plane.getBoundingClientRect().width;
        deck.resize(); fitThumbs();
        try { localStorage.setItem("lmr-sidebar-w", String(w)); } catch (e) { /**/ }
      };
      resizer.addEventListener("pointerdown", (e) => {
        if (mode !== "sidebar") return;
        e.preventDefault();
        resizer.setPointerCapture(e.pointerId);
        document.body.classList.add("lmr-col-resizing");
        const move = (ev) => setWidth(ev.clientX);
        const up = () => {
          document.body.classList.remove("lmr-col-resizing");
          resizer.removeEventListener("pointermove", move);
          resizer.removeEventListener("pointerup", up);
          resizer.removeEventListener("pointercancel", up);
        };
        resizer.addEventListener("pointermove", move);
        resizer.addEventListener("pointerup", up);
        resizer.addEventListener("pointercancel", up);
      });
    }

    function show(layout) {
      build();
      mode = layout;
      const isGrid = layout === "grid";
      plane.hidden = false;
      plane.classList.toggle("is-grid", isGrid);
      plane.classList.toggle("is-sidebar", !isGrid);
      deck.el.classList.toggle("is-gridded", isGrid);
      deck.el.classList.toggle("is-docked", !isGrid);
      deck.wheelNav = false;                 // the overview owns the wheel (scroll)
      deck.viewportInset = isGrid ? 0 : plane.getBoundingClientRect().width;
      deck.resize();                 // (re)fit the deck: reduced area when docked
      fitThumbs();                   // set --thumb-scale from the rendered width
      markCurrentThumb();
      const cur = plane.querySelector(".overview-thumb.is-current");
      if (cur) { cur.scrollIntoView?.({ block: "nearest" }); if (isGrid) selectThumb(cur); }
    }

    function toPresent() {
      mode = "present";
      if (plane) plane.hidden = true;
      deck.el.classList.remove("is-gridded", "is-docked");
      deck.wheelNav = true;
      deck.viewportInset = 0;
      deck.resize();
    }

    function toggle(layout) { mode === layout ? toPresent() : show(layout); }
    function gotoSlide(i) { toPresent(); deck.go(i, 0); }

    function fitThumbs() {
      const box = plane && plane.querySelector(".overview-thumb-stage");
      if (box && box.clientWidth > 0)
        plane.style.setProperty("--thumb-scale", String(box.clientWidth / deck.W));
    }

    function markCurrentThumb() {
      if (!plane) return;
      for (const t of plane.querySelectorAll(".overview-thumb")) {
        const cur = Number(t.dataset.slide) === deck.i;
        t.classList.toggle("is-current", cur);
        if (cur && mode === "sidebar") t.scrollIntoView?.({ block: "nearest" });
      }
    }

    function selectThumb(thumb) {
      for (const t of plane.querySelectorAll(".overview-thumb.is-selected"))
        t.classList.remove("is-selected");
      thumb.classList.add("is-selected");
      thumb.focus();
      thumb.scrollIntoView?.({ block: "nearest" });
    }

    /** Move the grid selection to the geometrically-nearest thumb in a direction. */
    function gridMove(key) {
      const thumbs = [...plane.querySelectorAll(".overview-thumb")];
      const cur = plane.querySelector(".overview-thumb.is-selected") || thumbs[0];
      if (!cur) return;
      const cr = cur.getBoundingClientRect();
      const cx = cr.left + cr.width / 2, cy = cr.top + cr.height / 2;
      const horiz = key === "ArrowRight" || key === "ArrowLeft";
      let best = null, score = Infinity;
      for (const t of thumbs) {
        if (t === cur) continue;
        const r = t.getBoundingClientRect();
        const dx = r.left + r.width / 2 - cx, dy = r.top + r.height / 2 - cy;
        if (key === "ArrowRight" && dx <= 1) continue;
        if (key === "ArrowLeft" && dx >= -1) continue;
        if (key === "ArrowDown" && dy <= 1) continue;
        if (key === "ArrowUp" && dy >= -1) continue;
        const along = horiz ? Math.abs(dx) : Math.abs(dy);
        const cross = horiz ? Math.abs(dy) : Math.abs(dx);
        const sc = along + cross * 3;          // prefer the same row/column
        if (sc < score) { score = sc; best = t; }
      }
      if (best) selectThumb(best);
    }

    /** The overview's key handler (registered with the core). Returns true when
     *  it consumes the event: in the modal grid it owns navigation; otherwise it
     *  owns only the toggle keys (o / O / Esc). */
    function onKey(e) {
      if (mode === "grid") {
        const thumbs = [...plane.querySelectorAll(".overview-thumb")];
        switch (e.key) {
          case "ArrowRight": case "ArrowLeft": case "ArrowUp": case "ArrowDown":
            gridMove(e.key); return true;
          case "Home": if (thumbs[0]) selectThumb(thumbs[0]); return true;
          case "End": if (thumbs.length) selectThumb(thumbs[thumbs.length - 1]); return true;
          case "Enter": case " ": {
            const sel = plane.querySelector(".overview-thumb.is-selected");
            if (sel) gotoSlide(Number(sel.dataset.slide));
            return true;
          }
          case "o": case "Escape": toPresent(); return true;
          default: return false;
        }
      }
      switch (e.key) {
        case "o": toggle("grid"); return true;       // 'o' = Slide Sorter grid
        case "O": toggle("sidebar"); return true;    // 'O' (Shift+o) = sidebar
        case "Escape": if (mode !== "present") { toPresent(); return true; } return false;
        default: return false;
      }
    }

    deck.addKeyHandler(onKey);
    deck.on("show", () => markCurrentThumb());                  // sidebar tracks
    deck.on("layout", () => { if (mode !== "present") fitThumbs(); });
    return (deck.overview = { build, toggle, gotoSlide,
      get mode() { return mode; } });
  }

  /** Boot the deck: the slide DOM is already present (rendered at build time by
   *  lemur.html); create a source-agnostic deck, attach the core presenter
   *  features (overview, print) and the lemur bridge to its hooks, then start it.
   *  Idempotent. */
  function init(el) {
    if (!el || el._lmrDeck) return el && el._lmrDeck;
    const deck = new Deck(el);
    el._lmrDeck = deck;
    el.classList.add("js");            // enables the interactive layout
    createOverview(deck);              // source-agnostic presenter features
    createPrint(deck);
    attachLemur(deck);                 // source-specific bridge
    deck.start();
    return deck;
  }

  return {
    computeScale: computeScale,
    slideStepCount: slideStepCount,
    stepInSpec: stepInSpec,
    applyStep: applyStep,
    freezeStage: freezeStage,
    toDesignCoords: toDesignCoords,
    arrowEndpoints: arrowEndpoints,
    connectEndpoints: connectEndpoints,
    drawArrow: drawArrow,
    parseHash: parseHash,
    formatHash: formatHash,
    clampLocation: clampLocation,
    Deck: Deck,
    createOverview: createOverview,
    createPrint: createPrint,
    attachLemur: attachLemur,
    init: init,
    contractVersion: 3              // the display contract (spec/display-contract.md)
  };
});
