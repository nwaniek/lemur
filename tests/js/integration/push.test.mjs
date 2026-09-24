// Push transition + arrows. Annotations and connectors are measured and drawn
// in the .stage-content coordinate frame — the element the 'push' transition
// actually translates — so they stay locked to their marks even when a slide is
// reached by STEPPING (its content is mid-transform at first-show) and when its
// arrows are frozen while the slide is parked off-stage (overview / print
// measureAll). Measuring against the untransformed .stage instead threw both a
// full design-width (1920) off. Fixture: example/push_arrows.lmr (also the
// user-facing documentation for the feature). Regression for fix B.
import { test, before, after } from "node:test";
import assert from "node:assert/strict";
import { buildDeck, launch } from "./helpers.mjs";

let deck, browser, page;

before(async () => {
  deck = buildDeck("example/push_arrows.lmr");   // 0:cover 1:intro 2:annotated 3:connector
  browser = await launch();
  page = await browser.newPage();
  await page.setViewport({ width: 1280, height: 720 });
  await page.goto(deck.url, { waitUntil: "load" });
  await page.evaluate(() => window.MathJax.startup.promise);
  await new Promise((r) => setTimeout(r, 300));
});

after(async () => {
  if (browser) await browser.close();
  if (deck) deck.cleanup();
});

// Reach (i, s) by STEPPING across the slide boundary, so slide i's first show —
// and thus its arrows' first (cached) measurement — happens during a push, with
// the incoming content still transformed. Then let the push + math settle.
async function stepInto(i, s) {
  await page.evaluate((j) => {
    const d = document.querySelector(".deck")._lmrDeck;
    d.go(j - 1, d.steps[j - 1] || 0);            // sit on the previous slide
  }, i);
  await new Promise((r) => setTimeout(r, 150));
  await page.evaluate((t) => {
    const d = document.querySelector(".deck")._lmrDeck;
    while (d.i < t.i || d.s < t.s) d.next();      // step across into the target
  }, { i, s });
  await new Promise((r) => setTimeout(r, 700));
}

// Worst gap (design px) from any arrow endpoint to its target's box, over the
// given slide indices (default: the current slide). 0 when the tip sits inside
// the box; ~standoff when just outside; ~1920 for the pre-fix stage-frame bug.
// Measured in each slide's own .stage-content frame, so it is invariant to any
// (parked / mid-transition) transform on that content.
function worstBoxGap(indices) {
  return page.evaluate((idxs) => {
    const d = document.querySelector(".deck")._lmrDeck;
    const list = idxs || [d.i];
    const boxGap = (x1, y1, r, o) => {
      const bx0 = (r.left - o.left) / d.scale, bx1 = (r.right - o.left) / d.scale;
      const by0 = (r.top - o.top) / d.scale, by1 = (r.bottom - o.top) / d.scale;
      return Math.hypot(Math.max(bx0 - x1, 0, x1 - bx1),
        Math.max(by0 - y1, 0, y1 - by1));
    };
    let worst = 0, n = 0;
    for (const i of list) {
      const slide = d.slides[i];
      const content = slide.querySelector(".stage-content");
      const o = content.getBoundingClientRect();
      for (const g of content.querySelectorAll("svg.arrow-layer g.arrow")) {
        n++;
        const to = g.getAttribute("data-to");
        const nums = g.querySelector("path").getAttribute("d")
          .match(/-?\d+(?:\.\d+)?/g).map(Number);
        const x1 = nums[nums.length - 2], y1 = nums[nums.length - 1];
        let best = Infinity;
        for (const t of slide.querySelectorAll("." + to))
          best = Math.min(best, boxGap(x1, y1, t.getBoundingClientRect(), o));
        worst = Math.max(worst, best);
      }
    }
    return { n, worst: Math.round(worst) };
  }, indices);
}

test("the arrow overlay lives inside .stage-content so it rides the push",
  async () => {
    const inside = await page.evaluate(() => {
      const svg = document.querySelector("svg.arrow-layer");
      return !!svg && svg.parentElement.classList.contains("stage-content");
    });
    // (an overlay exists because the deck was already navigated by earlier setup;
    //  if not yet, step into the annotated slide first)
    if (!inside) { await stepInto(2, 3); }
    assert.ok(await page.evaluate(() => {
      const svg = document.querySelector("svg.arrow-layer");
      return !!svg && svg.parentElement.classList.contains("stage-content");
    }), "arrow-layer is a child of .stage-content");
  });

test("annotation arrows stay on target when the slide is stepped into (push)",
  async () => {
    await stepInto(2, 3);                          // annotated eq at its final step
    const r = await worstBoxGap();
    assert.equal(r.n, 3, "three annotation arrows drawn");
    assert.ok(r.worst < 60, `each tip within ${r.worst}px of its mark (pre-fix ~1920)`);
  });

test("a connector stays on target when its slide is stepped into (push)",
  async () => {
    await stepInto(3, 1);                          // connector revealed at step 1
    const r = await worstBoxGap();
    assert.equal(r.n, 1, "one connector drawn");
    assert.ok(r.worst < 60, `tip within ${r.worst}px of its mark (pre-fix ~1920)`);
  });

test("overview measureAll keeps arrows on target for parked, transformed slides",
  async () => {
    // a fresh page so measureAll is the FIRST to measure the arrow slides — and
    // it does so while they are parked off-stage (is-after, translated +design-w)
    const p = await browser.newPage();
    await p.setViewport({ width: 1280, height: 720 });
    await p.goto(deck.url, { waitUntil: "load" });
    await p.evaluate(() => window.MathJax.startup.promise);
    await new Promise((r) => setTimeout(r, 300));
    const r = await p.evaluate(() => {
      const d = document.querySelector(".deck")._lmrDeck;
      d.overview.build();                          // beforeFreeze -> measureAll
      const boxGap = (x1, y1, r, o) => {
        const bx0 = (r.left - o.left) / d.scale, bx1 = (r.right - o.left) / d.scale;
        const by0 = (r.top - o.top) / d.scale, by1 = (r.bottom - o.top) / d.scale;
        return Math.hypot(Math.max(bx0 - x1, 0, x1 - bx1),
          Math.max(by0 - y1, 0, y1 - by1));
      };
      let worst = 0, n = 0;
      for (const i of [2, 3]) {
        const slide = d.slides[i];
        const content = slide.querySelector(".stage-content");
        const o = content.getBoundingClientRect();
        for (const g of content.querySelectorAll("svg.arrow-layer g.arrow")) {
          n++;
          const to = g.getAttribute("data-to");
          const nums = g.querySelector("path").getAttribute("d")
            .match(/-?\d+(?:\.\d+)?/g).map(Number);
          const x1 = nums[nums.length - 2], y1 = nums[nums.length - 1];
          let best = Infinity;
          for (const t of slide.querySelectorAll("." + to))
            best = Math.min(best, boxGap(x1, y1, t.getBoundingClientRect(), o));
          worst = Math.max(worst, best);
        }
      }
      return { n, worst: Math.round(worst) };
    });
    await p.close();
    assert.equal(r.n, 4, "all four arrows measured across the parked slides");
    assert.ok(r.worst < 60, `parked-slide tips within ${r.worst}px (pre-fix ~1920)`);
  });
