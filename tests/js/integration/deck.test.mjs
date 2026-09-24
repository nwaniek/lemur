// M1 integration test: the example deck loads headless, has the right slide
// count, scales, navigates, round-trips the hash, and carries no reveal.
import { test, before, after } from "node:test";
import assert from "node:assert/strict";
import { buildDeck, launch, CURRENT_INDEX } from "./helpers.mjs";

let deck, browser, page;

before(async () => {
  deck = buildDeck("example/master.lmr");
  browser = await launch();
  page = await browser.newPage();
  await page.setViewport({ width: 1600, height: 900 });
  await page.goto(deck.url, { waitUntil: "load" });
});

after(async () => {
  if (browser) await browser.close();
  if (deck) deck.cleanup();
});

test("deck has the expected slide count and one current slide", async () => {
  const count = await page.$$eval(".deck > .slide", els => els.length);
  assert.ok(count >= 13, `at least the baseline slides (got ${count})`);
  const current = await page.$$eval(".slide.is-current", els => els.length);
  assert.equal(current, 1);
  assert.equal(await page.evaluate(CURRENT_INDEX), 0); // cover shown first
});

test("no reveal artifacts are present at runtime", async () => {
  assert.equal(await page.evaluate("typeof window.Reveal"), "undefined");
  assert.equal(await page.$$eval(".reveal, .fragment, .r-stack",
    els => els.length), 0);
});

test("bundled fonts load and drive layout (deterministic across machines)",
  async () => {
    // the deck must lay out with its own OFL fonts, not whatever the machine
    // happens to have installed — otherwise metrics (and Safari overflow) drift
    const failed = [];
    page.on("requestfailed", (r) => {
      if (/\.woff2/.test(r.url())) failed.push(r.url());
    });
    await page.reload({ waitUntil: "networkidle0" });
    await page.evaluate(() => document.fonts.ready);
    const r = await page.evaluate(() => {
      const p = document.querySelector(".slide.is-current p")
        || document.querySelector(".stage p");
      return {
        family: p && getComputedStyle(p).fontFamily,
        // the variable font must cover the heading weight (650) exactly
        sans: document.fonts.check('40px "Source Sans 3"'),
        sans650: document.fonts.check('650 40px "Source Sans 3"'),
        loaded: [...document.fonts].some(
          (f) => f.family === "Source Sans 3" && f.status === "loaded"),
      };
    });
    assert.equal(failed.length, 0, `no woff2 failed to load (${failed})`);
    assert.ok(r.sans && r.sans650 && r.loaded, "Source Sans 3 loaded (incl. 650)");
    assert.match(r.family, /^"Source Sans 3"/, "body text uses the bundled font");
  });

test("the stage is scaled uniformly to fit the viewport", async () => {
  const info = await page.evaluate(() => {
    const deck = document.querySelector(".deck");
    const W = +deck.dataset.designW, H = +deck.dataset.designH;
    return {
      scale: +getComputedStyle(deck).getPropertyValue("--scale").trim(),
      expected: Math.min(window.innerWidth / W, window.innerHeight / H),
      t: getComputedStyle(document.querySelector(".slide.is-current .stage"))
        .transform
    };
  });
  assert.ok(Math.abs(info.scale - info.expected) < 1e-6, JSON.stringify(info));
  // the transform matrix's x-scale equals --scale and there is no skew
  const m = info.t.match(/matrix\(([-\d.]+),\s*([-\d.]+),/);
  assert.ok(m, info.t);
  assert.ok(Math.abs(Number(m[1]) - info.scale) < 1e-3, info.t);
  assert.equal(Number(m[2]), 0);
});

test("the design box does not shrink below the viewport width", async () => {
  // regression: the stage is a flex child; without flex-shrink:0 it collapses
  // to a narrow viewport and content reflows (design box must stay fixed).
  await page.setViewport({ width: 1000, height: 900 });
  const res = await page.evaluate(() => {
    const d = document.querySelector(".deck")._lmrDeck;
    const st = document.querySelector(".slide.is-current .stage")
      .getBoundingClientRect();
    return { designW: Math.round(st.width / d.scale),
             expected: +document.querySelector(".deck").dataset.designW };
  });
  assert.equal(res.designW, res.expected);   // stays at design width, not ~1000
  await page.setViewport({ width: 1600, height: 900 }); // restore
});

test("ArrowRight advances the current slide; hash round-trips", async () => {
  assert.equal(await page.evaluate(() => location.hash), "#/0/0");
  await page.keyboard.press("ArrowRight");
  assert.equal(await page.evaluate(CURRENT_INDEX), 1);
  assert.equal(await page.evaluate(() => location.hash), "#/1/0");
  await page.keyboard.press("ArrowLeft");
  assert.equal(await page.evaluate(CURRENT_INDEX), 0);

  // End jumps to the last slide, Home back to the first (index resolved live
  // so adding example slides does not break the test)
  const last = await page.$$eval(".deck > .slide", (e) => e.length - 1);
  await page.keyboard.press("End");
  assert.equal(await page.evaluate(CURRENT_INDEX), last);
  await page.keyboard.press("Home");
  assert.equal(await page.evaluate(CURRENT_INDEX), 0);
});

// current (slide, step) — read straight off the presenter
const loc = () => page.evaluate(() => {
  const d = document.querySelector(".deck")._lmrDeck; return { i: d.i, s: d.s };
});

test("the mouse wheel steps the deck: down = forward, up = back (throttled)",
  async () => {
    await page.mouse.move(800, 450);
    assert.deepEqual(await loc(), { i: 0, s: 0 });
    await page.mouse.wheel({ deltaY: 120 });                  // scroll down
    await new Promise((r) => setTimeout(r, 150));
    assert.deepEqual(await loc(), { i: 1, s: 0 }, "wheel down advanced one step");
    await page.mouse.wheel({ deltaY: -120 });                 // scroll up
    await new Promise((r) => setTimeout(r, 150));
    assert.deepEqual(await loc(), { i: 0, s: 0 }, "wheel up retreated one step");
    // a rapid momentum burst inside the throttle window collapses to one step
    await page.evaluate(() => {
      for (let k = 0; k < 5; k++)
        window.dispatchEvent(
          new WheelEvent("wheel", { deltaY: 120, cancelable: true }));
    });
    await new Promise((r) => setTimeout(r, 150));
    assert.deepEqual(await loc(), { i: 1, s: 0 }, "a wheel burst = a single step");
    await page.keyboard.press("Home");
  });

test("an incoming hash is honoured and clamped", async () => {
  await page.goto(deck.url + "#/99/99", { waitUntil: "load" });
  const last = await page.$$eval(".deck > .slide", (e) => e.length - 1);
  assert.equal(await page.evaluate(CURRENT_INDEX), last); // clamped to last
});

// index of the slide with a given id (resolved live)
const idxOf = (id) => page.evaluate((x) => Array.prototype.findIndex.call(
  document.querySelectorAll(".deck > .slide"), (s) => s.id === x), id);

test("reference and citation links navigate to their slide", async () => {
  const sum = await idxOf("sum_product"), refs = await idxOf("refs");
  // a slide reference (@sum_product -> #/sum_product)
  await page.goto(deck.url + "#/2/2", { waitUntil: "load" });
  await page.evaluate(() => window.MathJax.startup.promise);
  await page.evaluate(() => {
    const a = Array.prototype.find.call(
      document.querySelectorAll(".slide.is-current a"),
      (a) => a.getAttribute("href") === "#/sum_product");
    a.click();
  });
  await new Promise((r) => setTimeout(r, 80));
  assert.equal(await page.evaluate(CURRENT_INDEX), sum);
  assert.equal(await page.evaluate(() => location.hash), `#/${sum}/0`);

  // a bibliography citation ([1] -> #/refs, the slide it is defined on)
  await page.goto(deck.url + "#/4/0", { waitUntil: "load" });
  await page.evaluate(() => window.MathJax.startup.promise);
  // fire the click on the anchor itself (like the reference link above) rather
  // than via page.click(): the superscript is tiny and mid-reflow after MathJax,
  // so computing a clickable point races the layout — a DOM click doesn't.
  await page.evaluate(() =>
    document.querySelector(".slide.is-current .lmr-cite a").click());
  await new Promise((r) => setTimeout(r, 80));
  assert.equal(await page.evaluate(CURRENT_INDEX), refs);

  // an incoming named hash on load resolves too
  await page.goto(deck.url + "#/sum_product", { waitUntil: "load" });
  await new Promise((r) => setTimeout(r, 80));
  assert.equal(await page.evaluate(CURRENT_INDEX), sum);
});

// logical visibility (the is-visible class, set instantly by the step model) of
// the current slide's data-appear element whose text contains t. The class is
// the source of truth; the CSS animates the appear/disappear around it.
function visOf(t) {
  return page.evaluate((needle) => {
    const el = Array.from(document.querySelectorAll(
      ".slide.is-current [data-appear]"))
      .find((e) => e.textContent.includes(needle));
    if (!el) return "missing";
    return el.classList.contains("is-visible") ? "visible" : "hidden";
  }, t);
}

test("a fragmented slide steps its elements in and out", async () => {
  // slide 2 = "Why graphical models?": one '+' item (step 1), then a '!pause'
  // group (step 2). Base content is visible from step 0.
  const PLUS = "asynchronous, distributed algorithms shine";
  const PAUSE = "The plan for today";
  await page.goto(deck.url + "#/2/0", { waitUntil: "load" });
  assert.equal(await visOf(PLUS), "hidden");
  assert.equal(await visOf(PAUSE), "hidden");

  await page.keyboard.press("ArrowRight"); // -> step 1
  assert.equal(await page.evaluate(() => location.hash), "#/2/1");
  assert.equal(await visOf(PLUS), "visible");
  assert.equal(await visOf(PAUSE), "hidden");

  await page.keyboard.press("ArrowRight"); // -> step 2
  assert.equal(await page.evaluate(() => location.hash), "#/2/2");
  assert.equal(await visOf(PLUS), "visible");
  assert.equal(await visOf(PAUSE), "visible");

  await page.keyboard.press("ArrowLeft"); // back to step 1: pause group hides
  assert.equal(await visOf(PAUSE), "hidden");
  assert.equal(await visOf(PLUS), "visible");
});

test("equation segments color cumulatively across steps", async () => {
  // slide 5 = "The sum-product update": three '\mk' marks coloured by an
  // !annotate at steps 2 (prod), 3 (fac), 4 (sum).
  await page.goto(deck.url + "#/5/1", { waitUntil: "load" });
  await page.evaluate(() => window.MathJax.startup.promise);
  // decorate() stamps data-hl once math is rendered
  await page.waitForFunction(() =>
    !!document.querySelector(".slide.is-current .lmr-a-prod") &&
    !!document.querySelector(".slide.is-current .lmr-a-prod").dataset.hl);
  const hl = () => page.evaluate(() => {
    const g = (n) => {
      const el = document.querySelector(".slide.is-current .lmr-a-" + n);
      return el ? el.classList.contains("is-hl") : null;
    };
    return { sum: g("sum"), fac: g("fac"), prod: g("prod") };
  });
  assert.deepEqual(await hl(), { sum: false, fac: false, prod: false });
  await page.keyboard.press("ArrowRight"); // step 2: prod
  assert.deepEqual(await hl(), { sum: false, fac: false, prod: true });
  await page.keyboard.press("ArrowRight"); // step 3: fac
  await page.keyboard.press("ArrowRight"); // step 4: sum
  assert.deepEqual(await hl(), { sum: true, fac: true, prod: true });
  await page.keyboard.press("ArrowLeft"); // back to step 3: sum uncolors
  assert.deepEqual(await hl(), { sum: false, fac: true, prod: true });
});

test("stepping rolls over slide boundaries", async () => {
  // from the last step of slide 2, ArrowRight rolls into slide 3 at step 0
  await page.goto(deck.url + "#/2/2", { waitUntil: "load" });
  await page.keyboard.press("ArrowRight");
  assert.equal(await page.evaluate(CURRENT_INDEX), 3);
  assert.equal(await page.evaluate(() => location.hash), "#/3/0");
  // and ArrowLeft rolls back to slide 2's last step
  await page.keyboard.press("ArrowLeft");
  assert.equal(await page.evaluate(CURRENT_INDEX), 2);
  assert.equal(await page.evaluate(() => location.hash), "#/2/2");
});
