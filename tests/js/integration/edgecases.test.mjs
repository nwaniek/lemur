// Edge cases and error handling: the deck is built at runtime from the embedded
// AST (JS is required), malformed-equation error box, fade + reduced-motion, and
// content overflow clipping.
import { test, before, after } from "node:test";
import assert from "node:assert/strict";
import { buildDeck, buildDeckFromSource, launch } from "./helpers.mjs";

let browser;
before(async () => { browser = await launch(); });
after(async () => { if (browser) await browser.close(); });

test("the progress bar (opt-in) tracks the deck position across steps", async () => {
  const deck = buildDeckFromSource(
    "!progress bottom\n!slide One\nbase\n\n+ later\n!slide Two\ny\n");
  const page = await browser.newPage();
  await page.goto(deck.url, { waitUntil: "load" });
  const scaleX = () => page.evaluate(() => {
    const el = document.querySelector(".deck-progress");
    return el ? +new DOMMatrix(getComputedStyle(el).transform).a.toFixed(2) : null;
  });
  const pos = await page.evaluate(() =>
    document.querySelector(".deck-progress").getAttribute("data-pos"));
  assert.equal(pos, "bottom");
  assert.equal(await scaleX(), 0);                 // at the very first stop
  await page.evaluate(() => document.querySelector(".deck")._lmrDeck.last());
  await new Promise((r) => setTimeout(r, 400));     // let the 0.3s bar settle
  assert.equal(await scaleX(), 1);                 // at the very last stop
  await page.close();
  deck.cleanup();
});

test("the deck DOM is rendered at build time (present without JS, no AST)", async () => {
  const deck = buildDeckFromSource(
    "!title A Talk\n!slide First\nvisible base content here\n");
  const page = await browser.newPage();
  // with JS disabled the slides must still be there — proving they were
  // rendered at build time (lemur.emit.html), not built by the runtime
  await page.setJavaScriptEnabled(false);
  await page.goto(deck.url, { waitUntil: "load" });
  const built = await page.evaluate(() => ({
    hasAst: !!document.getElementById("lmr-deck"),
    slides: document.querySelectorAll(".deck > .slide").length,
    shows: [...document.querySelectorAll(".slide")]
      .some((s) => s.textContent.includes("visible base content here")),
  }));
  assert.equal(built.hasAst, false, "no embedded AST — the product does not depend on it");
  assert.ok(built.slides >= 1, "the slide DOM is in the shipped HTML");
  assert.ok(built.shows, "slide content is server-rendered");
  await page.close();
  deck.cleanup();
});

test("a malformed equation yields an error box, not a blank slide", async () => {
  const deck = buildDeckFromSource(
    "!slide Bad\ngood $a^2$ here\n\n:: math\n\t\\left( x + \\notacmd{y}\n\n" +
    "text after the broken equation\n");
  const page = await browser.newPage();
  const errors = [];
  page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
  await page.goto(deck.url, { waitUntil: "networkidle0" });
  await page.evaluate(() => window.MathJax.startup.promise);
  await new Promise((r) => setTimeout(r, 300));
  const info = await page.evaluate(() => {
    const s = document.querySelector(".slide.is-current");
    return {
      hasErrorBox: !!s.querySelector("[data-mjx-error]"),
      goodMath: s.querySelectorAll("mjx-container").length >= 2,
      textAfter: s.textContent.includes("text after the broken equation"),
      notBlank: s.textContent.trim().length > 0
    };
  });
  assert.ok(info.hasErrorBox, "a visible error box is rendered");
  assert.ok(info.goodMath, "the good equation still renders");
  assert.ok(info.textAfter && info.notBlank, "the slide is not blanked");
  assert.ok(errors.some((e) => /math error/.test(e)), "logged to the console");
  await page.close();
  deck.cleanup();
});

test("slide + step transitions are independent; reduced-motion disables them",
  async () => {
    // slide=fade (cross-fade), step=none
    const deck = buildDeckFromSource(
      "!transition fade none\n!slide One\nalpha\n\n!pause\n\nbeta\n" +
      "!slide Two\ngamma\n");
    const page = await browser.newPage();
    await page.goto(deck.url + "#/1/0", { waitUntil: "load" });
    const s = await page.evaluate(() => ({
      slideTrans: getComputedStyle(document.querySelector(".slide.is-current"))
        .transitionProperty,
      deckStep: document.querySelector(".deck").dataset.stepTransition
    }));
    assert.match(s.slideTrans, /opacity/);   // cross-fade transition present
    assert.equal(s.deckStep, "none");        // step transition off as requested

    // reduced motion disables the slide transition
    await page.emulateMediaFeatures(
      [{ name: "prefers-reduced-motion", value: "reduce" }]);
    await page.goto(deck.url + "#/1/0", { waitUntil: "load" });
    const dur = await page.evaluate(() =>
      getComputedStyle(document.querySelector(".slide.is-current"))
        .transitionDuration);
    assert.equal(dur, "0s");
    await page.close();
    deck.cleanup();
  });

test("default transitions: no slide fade, elements fade in on step", async () => {
  // defaults are slide=none, step=fade
  const deck = buildDeckFromSource("!slide A\nx\n!slide B\ny\n");
  const page = await browser.newPage();
  await page.goto(deck.url, { waitUntil: "load" });
  const d = await page.evaluate(() => {
    const deck = document.querySelector(".deck");
    return { slide: deck.dataset.transition, step: deck.dataset.stepTransition };
  });
  assert.equal(d.slide, "none");
  assert.equal(d.step, "fade");
  await page.close();
  deck.cleanup();
});

test("slide-in transition pushes the outgoing slide out; items rise", async () => {
  const deck = buildDeckFromSource(
    "!transition slide rise\n!slide One\nfirst\n\n+ a rising item\n" +
    "!slide Two\nsecond\n");
  const page = await browser.newPage();
  await page.setViewport({ width: 1200, height: 700 });
  await page.goto(deck.url, { waitUntil: "load" });
  const wait = (ms) => new Promise((r) => setTimeout(r, ms));
  const tx = (sel) => page.evaluate((s) => {
    var el = document.querySelector(s);
    return Math.round(new DOMMatrix(getComputedStyle(el).transform).m41);
  }, sel);
  // forward from One to Two; let the slide transition settle
  await page.evaluate(() => document.querySelector(".deck")._lmrDeck.go(0, 0));
  await wait(50);
  await page.evaluate(() => document.querySelector(".deck")._lmrDeck.go(1, 0));
  await wait(700);
  assert.equal(await tx(".slide.is-current"), 0, "incoming slide centred");
  const curId = await page.evaluate(() =>
    document.querySelector(".slide.is-current").id);
  assert.match(curId, /^two/);
  // the '+' item on One rises: rise is a transition on opacity AND transform
  // (fade transitions opacity only), reversible on step-back
  await page.evaluate(() => document.querySelector(".deck")._lmrDeck.go(0, 1));
  await wait(30);
  const props = await page.evaluate(() => {
    var it = [...document.querySelectorAll(".slide.is-current [data-appear]")]
      .find((e) => e.classList.contains("is-visible"));
    return it ? getComputedStyle(it).transitionProperty : "none";
  });
  assert.match(props, /transform/);
  await page.close();
  deck.cleanup();
});

test("push transition moves only the content; the header stays put", async () => {
  const deck = buildDeckFromSource(
    "!title T\n!header Fixed Header\n!transition push\n" +
    "!slide One\nfirst\n!slide Two\nsecond\n");
  const page = await browser.newPage();
  await page.setViewport({ width: 1200, height: 700 });
  await page.goto(deck.url, { waitUntil: "load" });
  const wait = (ms) => new Promise((r) => setTimeout(r, ms));
  const tx = (sel) => page.evaluate((s) => {
    var el = document.querySelector(s);
    return el ? Math.round(new DOMMatrix(getComputedStyle(el).transform).m41) : null;
  }, sel);
  // to the first content slide (index 1; index 0 is the cover), then push to 2
  await page.evaluate(() => document.querySelector(".deck")._lmrDeck.go(1, 0));
  await wait(700);
  await page.evaluate(() => document.querySelector(".deck")._lmrDeck.go(2, 0));
  await wait(200);                                   // mid-transition
  const midContent = await tx(".slide.is-current .stage-content");
  const midHeader = await tx(".slide.is-current .lmr-header");
  assert.ok(midContent > 20, "content is mid-slide, not yet centred");
  assert.equal(midHeader, 0, "header does not move");
  await wait(600);                                   // settle
  assert.equal(await tx(".slide.is-current .stage-content"), 0, "content centred");
  await page.close();
  deck.cleanup();
});

test("prose is emphasised (bold/color) on a step, with no arrow", async () => {
  const deck = buildDeckFromSource(
    "!slide Emph\nA [bold part]^a and a [red part]^b here.\n\n" +
    "!annotate\n\ta[.bold]:\n\tb[#c0392b]:\n");
  const page = await browser.newPage();
  await page.setViewport({ width: 1400, height: 800 });
  await page.goto(deck.url + "#/0/2", { waitUntil: "load" }); // both active
  await page.evaluate(() => window.MathJax.startup.promise);
  await page.waitForFunction(() =>
    document.querySelector(".slide.is-current .lmr-a-a") &&
    document.querySelector(".slide.is-current .lmr-a-a").dataset.hl);
  await new Promise((r) => setTimeout(r, 400)); // let the color transition settle
  const res = await page.evaluate(() => {
    const cs = (sel) => getComputedStyle(
      document.querySelector(".slide.is-current " + sel));
    return {
      aWeight: cs(".lmr-a-a").fontWeight,
      aColor: cs(".lmr-a-a").color,       // bold => color unchanged
      bColor: cs(".lmr-a-b").color,
      arrows: document.querySelectorAll(".slide.is-current g.arrow").length
    };
  });
  assert.equal(res.aWeight, "700");                 // bold
  assert.equal(res.aColor, "rgb(35, 38, 41)");      // not recolored
  assert.equal(res.bColor, "rgb(192, 57, 43)");     // #c0392b
  assert.equal(res.arrows, 0);                      // pure emphasis, no arrows
  await page.close();
  deck.cleanup();
});

test("two annotated equations on one slide resolve to their own anchors",
  async () => {
    const deck = buildDeckFromSource(
      "!slide Two eqs\n" +
      ":: math\n\t\\mk{alpha}{\\alpha}\n\n!annotate\n\talpha: first eq\n\n" +
      ":: math\n\t\\mk{beta}{\\beta}\n\n!annotate\n\tbeta: second eq\n");
    const page = await browser.newPage();
    await page.setViewport({ width: 1400, height: 800 });
    await page.goto(deck.url + "#/0/2", { waitUntil: "load" }); // both steps
    await page.evaluate(() => window.MathJax.startup.promise);
    await page.waitForFunction(() =>
      document.querySelector(".slide.is-current .lmr-a-alpha") &&
      document.querySelector(".slide.is-current .lmr-a-alpha").dataset.hl);
    const res = await page.evaluate(() => {
      const s = document.querySelector(".slide.is-current");
      const g = (n) => s.querySelector(".lmr-a-" + n);
      const arrowTo = (n) =>
        !!s.querySelector('svg.arrow-layer g.arrow[data-to="lmr-a-' + n + '"]');
      return {
        // each mark is its own class anchor on this slide (no deck-wide ids)
        alphaHl: g("alpha").classList.contains("is-hl"),
        betaHl: g("beta").classList.contains("is-hl"),
        alphaArrow: arrowTo("alpha"),
        betaArrow: arrowTo("beta"),
        arrows: s.querySelectorAll("svg.arrow-layer g.arrow").length
      };
    });
    assert.ok(res.alphaHl && res.betaHl, "both anchors colored at step 2");
    assert.ok(res.alphaArrow && res.betaArrow,
      "each mark's arrow targets its own class anchor");
    assert.equal(res.arrows, 2, "each equation gets its own arrow");
    await page.close();
    deck.cleanup();
  });

test("!connect draws a step-gated arrow between two same-line marks",
  async () => {
    const deck = buildDeckFromSource(
      "!slide Q&A\n" +
      "[what is computed]^q1 leads to [theory of computation]^a1\n\n" +
      "!connect\n\tq1 -> a1 [#c0392b]\n");
    const page = await browser.newPage();
    await page.setViewport({ width: 1400, height: 800 });
    // step 0: the marks are shown, the connector is not yet drawn/visible
    await page.goto(deck.url + "#/0/0", { waitUntil: "load" });
    await page.evaluate(() => window.MathJax.startup.promise);
    await page.waitForFunction(() => {
      const d = document.querySelector(".deck")._lmrDeck;
      return d && d.i === 0 && document.querySelector(".slide.is-current .lmr-a-a1");
    });
    const before = await page.evaluate(() => {
      const g = document.querySelector('.slide.is-current g.arrow[data-to="lmr-a-a1"]');
      return g ? getComputedStyle(g).visibility : "absent";
    });
    // step 1: the connector appears and its endpoint lands on the target mark
    await page.evaluate(() => document.querySelector(".deck")._lmrDeck.next());
    await page.waitForFunction(() => {
      const g = document.querySelector('.slide.is-current g.arrow[data-to="lmr-a-a1"]');
      return g && getComputedStyle(g).visibility === "visible";
    });
    const res = await page.evaluate(() => {
      const slide = document.querySelector(".slide.is-current");
      const g = slide.querySelector('g.arrow[data-to="lmr-a-a1"]');
      const nums = g.querySelector("path").getAttribute("d").match(/[-\d.]+/g).map(Number);
      const x1 = nums[nums.length - 2], y1 = nums[nums.length - 1];
      const deck = document.querySelector(".deck")._lmrDeck;
      const content = slide.querySelector(".stage-content");   // arrow measure frame
      const t = window.LMR.toDesignCoords(
        slide.querySelector(".lmr-a-a1").getBoundingClientRect(),
        content.getBoundingClientRect(), deck.scale);
      const col = g.querySelector("path").getAttribute("marker-end");
      return { x1, y1, t, col };
    });
    assert.equal(before, "hidden", "connector hidden before its step");
    assert.ok(res.col && res.col.includes("lmr-arrowhead"), "forward arrowhead");
    // horizontal connector: the head lands just left of the target's left edge
    assert.ok(res.x1 >= res.t.x - 14 && res.x1 <= res.t.x + 6,
      `x1=${res.x1} near left edge ${res.t.x}`);
    // and within the target's vertical span
    assert.ok(res.y1 >= res.t.y - 4 && res.y1 <= res.t.y + res.t.h + 4,
      `y1=${res.y1} within [${res.t.y}, ${res.t.y + res.t.h}]`);
    await page.close();
    deck.cleanup();
  });

test("multi-layer image with a non-100% width keeps its layers aligned",
  async () => {
    // the example's fg figure has 3 real SVG layers at !width 85%
    const deck = buildDeck("example/master.lmr");
    const page = await browser.newPage();
    await page.setViewport({ width: 1600, height: 900 });
    await page.goto(deck.url + "#/4/3", { waitUntil: "networkidle0" });
    await page.evaluate(() => window.MathJax.startup.promise);
    await new Promise((r) => setTimeout(r, 300));
    const same = await page.evaluate(() => {
      const imgs = [...document.querySelectorAll(".lmr-overlay img")];
      if (imgs.length < 3) return false;
      const r0 = imgs[0].getBoundingClientRect();
      return imgs.every((im) => {
        const r = im.getBoundingClientRect();
        return Math.abs(r.x - r0.x) < 1 && Math.abs(r.y - r0.y) < 1 &&
          Math.abs(r.width - r0.width) < 1 && Math.abs(r.height - r0.height) < 1;
      });
    });
    assert.ok(same, "all 3 layers share the same box");
    await page.close();
    deck.cleanup();
  });

test("overlay specs show/hide content per step (transient reveals)", async () => {
  const deck = buildDeckFromSource(
    "!slide Ov\n- always\n+<2-> from two\n-<3> only three\n+<4-> from four\n\n" +
    "!when<2-3>\n\tduring 2-3\n");
  const page = await browser.newPage();
  await page.setViewport({ width: 1400, height: 800 });
  // the is-visible class is the instant logical state (the css animates the
  // appear/disappear around it, so computed visibility lags on the way out)
  const vis = (needle) => page.evaluate((t) => {
    // a reveal spec renders as data-appear ("n-") or data-when (bounded); the
    // is-visible class is the source of truth either way
    const el = [...document.querySelectorAll(
      ".slide.is-current [data-when], .slide.is-current [data-appear]")]
      .find((e) => e.textContent.includes(t));
    return el ? (el.classList.contains("is-visible") ? "visible" : "hidden") : "missing";
  }, needle);
  const at = async (s) => {
    await page.goto(deck.url + "#/0/" + s, { waitUntil: "load" });
    await new Promise((r) => setTimeout(r, 40));
    return { from2: await vis("from two"), only3: await vis("only three"),
      block: await vis("during 2-3") };
  };
  assert.deepEqual(await at(1),
    { from2: "hidden", only3: "hidden", block: "hidden" });
  assert.deepEqual(await at(2),
    { from2: "visible", only3: "hidden", block: "visible" });
  assert.deepEqual(await at(3),
    { from2: "visible", only3: "visible", block: "visible" });
  assert.deepEqual(await at(4),   // transient/range items hide again
    { from2: "visible", only3: "hidden", block: "hidden" });
  await page.close();
  deck.cleanup();
});

test("columns render side by side; steps flow across them", async () => {
  const deck = buildDeckFromSource(
    "!slide Cols\n!columns[60,40]\n\t!column\n\t\tleft content\n\t\t!pause\n" +
    "\t\tleft second\n\t!column\n\t\tright content appears after the left pause\n");
  const page = await browser.newPage();
  await page.setViewport({ width: 1600, height: 900 });
  await page.goto(deck.url + "#/0/0", { waitUntil: "load" });
  await new Promise((r) => setTimeout(r, 200));
  const geo = await page.evaluate(() => {
    const cols = [...document.querySelectorAll(".slide.is-current .lmr-column")];
    return cols.map((c) => {
      const r = c.getBoundingClientRect();
      return { x: Math.round(r.x), w: Math.round(r.width) };
    });
  });
  assert.equal(geo.length, 2);
  assert.ok(geo[1].x > geo[0].x + geo[0].w - 5, "second column is to the right");
  assert.ok(Math.abs(geo[0].w / geo[1].w - 1.5) < 0.05, "widths are ~60/40");

  // the right column's content is gated at step 1 (a left-column pause), so it
  // is hidden at step 0
  const rightHidden = () => page.evaluate(() => {
    const el = [...document.querySelectorAll(".slide.is-current .lmr-column")][1]
      .querySelector("[data-appear]");
    return el ? (el.classList.contains("is-visible") ? "visible" : "hidden") : "no-gate";
  });
  assert.equal(await rightHidden(), "hidden");
  await page.keyboard.press("ArrowRight"); // step 1
  assert.equal(await rightHidden(), "visible");
  await page.close();
  deck.cleanup();
});

test("stack layers overlap in one cell and take each other's place", async () => {
  const deck = buildDeckFromSource(
    "!slide Stk\n!stack\n\t!layer<0>\n\t\tfirst layer\n" +
    "\t!layer<1->\n\t\tsecond layer is a good deal taller so the box grows\n" +
    "\t\tand still the summary below must never move\n" +
    "the summary line below the stack\n");
  const page = await browser.newPage();
  await page.setViewport({ width: 1600, height: 900 });
  const state = async (s) => {
    await page.goto(deck.url + "#/0/" + s, { waitUntil: "load" });
    await new Promise((r) => setTimeout(r, 60));
    return page.evaluate(() => {
      const layers = [...document.querySelectorAll(".slide.is-current .lmr-layer")];
      const boxes = layers.map((l) => l.getBoundingClientRect());
      const vis = layers.map((l) =>
        l.classList.contains("is-visible") ? "visible" : "hidden");
      const summary = [...document.querySelectorAll(".slide.is-current p")]
        .find((p) => p.textContent.includes("summary line"));
      return { vis, top0: Math.round(boxes[0].top), top1: Math.round(boxes[1].top),
        summaryTop: Math.round(summary.getBoundingClientRect().top) };
    });
  };
  const s0 = await state(0);
  // both layers share the same grid cell -> identical top (overlap)
  assert.equal(s0.top0, s0.top1, "layers overlap in one cell");
  assert.deepEqual(s0.vis, ["visible", "hidden"], "layer 0 only at step 0");
  const s1 = await state(1);
  assert.deepEqual(s1.vis, ["hidden", "visible"], "layer 1 takes its place");
  // the summary below never moves as the taller layer swaps in
  assert.equal(s0.summaryTop, s1.summaryTop, "content below the stack stays put");
  await page.close();
  deck.cleanup();
});

test("content taller than the design box is clipped, not bleeding out",
  async () => {
    // a long code block overflows 720px; the stage clips it (overflow:hidden)
    const lines = Array.from({ length: 80 }, (_, i) => `\tline ${i}`).join("\n");
    const deck = buildDeckFromSource(
      "!slide Tall\n:: text\n" + lines + "\n");
    const page = await browser.newPage();
    await page.setViewport({ width: 1280, height: 720 });
    const warnings = [];
    page.on("console", (m) => warnings.push(m.text()));
    await page.goto(deck.url + "?dev", { waitUntil: "networkidle0" });
    await new Promise((r) => setTimeout(r, 200));
    const res = await page.evaluate(() => {
      const stage = document.querySelector(".slide.is-current .stage");
      return {
        overflowFlagged: stage.classList.contains("stage--overflow"),
        clipped: getComputedStyle(stage).overflow === "hidden"
      };
    });
    assert.ok(res.clipped, "the stage clips overflow");
    assert.ok(res.overflowFlagged, "overflow is flagged in dev mode");
    assert.ok(warnings.some((w) => /overflows/.test(w)), "warned to console");
    await page.close();
    deck.cleanup();
  });
