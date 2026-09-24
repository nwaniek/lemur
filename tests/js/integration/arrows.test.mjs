// M4 integration test: arrows land on their target subexpression, at two
// viewport sizes and after a resize (Plan.md Section 4.5, acceptance 4).
import { test, before, after } from "node:test";
import assert from "node:assert/strict";
import { buildDeck, launch } from "./helpers.mjs";

let deck, browser, page;

before(async () => {
  deck = buildDeck("example/master.lmr");
  browser = await launch();
  page = await browser.newPage();
});

after(async () => {
  if (browser) await browser.close();
  if (deck) deck.cleanup();
});

// For the arrow targeting `anchorClass`, return its endpoint (design coords,
// read from the path) and the live target box (design coords).
function probe(anchorClass) {
  return page.evaluate((cls) => {
    const slide = document.querySelector(".slide.is-current");
    const g = slide.querySelector(
      'svg.arrow-layer g.arrow[data-to="' + cls + '"]');
    if (!g) return null;
    const nums = g.querySelector("path").getAttribute("d").match(/[-\d.]+/g)
      .map(Number);
    const x1 = nums[nums.length - 2], y1 = nums[nums.length - 1];
    const deck = document.querySelector(".deck")._lmrDeck;
    // arrows are measured in the .stage-content frame (transform-invariant), so
    // compare the endpoint to the target measured in that same frame
    const content = slide.querySelector(".stage-content");
    const t = window.LMR.toDesignCoords(
      slide.querySelector("." + cls).getBoundingClientRect(),
      content.getBoundingClientRect(), deck.scale);
    return { x1, y1, t };
  }, anchorClass);
}

async function assertLands(cls) {
  const p = await probe(cls);
  assert.ok(p, `arrow for ${cls} exists`);
  // the endpoint's x sits within the target's horizontal span (small tol)
  assert.ok(p.x1 >= p.t.x - 5 && p.x1 <= p.t.x + p.t.w + 5,
    `${cls}: x1=${p.x1} within [${p.t.x}, ${p.t.x + p.t.w}]`);
  // and its y sits just below the target's bottom edge (standoff gap)
  const bottom = p.t.y + p.t.h;
  assert.ok(p.y1 >= bottom - 1 && p.y1 <= bottom + 14,
    `${cls}: y1=${p.y1} just below bottom=${bottom}`);
}

async function gotoAllArrows(w, h) {
  await page.setViewport({ width: w, height: h });
  await page.goto(deck.url + "#/5/4", { waitUntil: "load" });
  await page.evaluate(() => window.MathJax.startup.promise);
  await page.waitForFunction(() =>
    document.querySelectorAll(".slide.is-current svg.arrow-layer g.arrow")
      .length >= 3);
}

test("arrows land on their targets at a wide viewport", async () => {
  await gotoAllArrows(1600, 900);
  for (const c of ["lmr-a-sum", "lmr-a-fac", "lmr-a-prod"]) await assertLands(c);
});

test("arrows land on their targets at a smaller, different-ratio viewport",
  async () => {
    await gotoAllArrows(1100, 820); // different scale and aspect
    for (const c of ["lmr-a-sum", "lmr-a-fac", "lmr-a-prod"]) {
      await assertLands(c);
    }
  });

test("arrows stay on target after a live resize", async () => {
  await gotoAllArrows(1600, 900);
  await assertLands("lmr-a-fac");
  // resize the window: the runtime re-measures on the resize event
  await page.setViewport({ width: 1280, height: 720 });
  await page.waitForFunction(() => true);
  await new Promise((r) => setTimeout(r, 100));
  for (const c of ["lmr-a-sum", "lmr-a-fac", "lmr-a-prod"]) await assertLands(c);
});

test("arrows are gated by their step", async () => {
  // an isolated page loaded straight at (5, 2): no shared-page history whose
  // async readiness (measure/applyState) could race this step-gating assertion
  const p = await browser.newPage();
  await p.setViewport({ width: 1600, height: 900 });
  await p.goto(deck.url + "#/5/2", { waitUntil: "load" });
  await p.evaluate(() => window.MathJax.startup.promise);
  // wait until the deck has settled at (5, 2) and its arrows are drawn (the
  // 'ready' hook measures the current slide once math + fonts are final)
  await p.waitForFunction(() => {
    const d = document.querySelector(".deck")._lmrDeck;
    return d && d.i === 5 && d.s === 2 &&
      document.querySelector(".slide.is-current svg.arrow-layer g.arrow");
  });
  const vis = await p.evaluate(() => {
    const g = (c) => document.querySelector(
      '.slide.is-current g.arrow[data-to="' + c + '"]');
    const isVis = (el) => el && getComputedStyle(el).visibility === "visible";
    return {
      prod: isVis(g("lmr-a-prod")), // step 2: visible
      fac: isVis(g("lmr-a-fac")),   // step 3: not yet
      sum: isVis(g("lmr-a-sum"))    // step 4: not yet
    };
  });
  assert.deepEqual(vis, { prod: true, fac: false, sum: false });
  await p.close();
});
