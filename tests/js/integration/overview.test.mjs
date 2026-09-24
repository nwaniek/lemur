// Slide Overview (Slide Sorter grid + docked sidebar): a key-toggled plane of
// thumbnails, each a frozen clone of a slide at its FINAL step, clickable to jump.
// See Plan-SlideOverview.md.
import { test, before, after } from "node:test";
import assert from "node:assert/strict";
import { buildDeckFromSource, launch } from "./helpers.mjs";

let deck, browser, page;

// six slides, one with a transient <1> element (to prove the final-variant view),
// enough to exceed a short viewport (overflow/scroll) in the sidebar
// no '!title' (which would synthesize a cover at index 0); slide One is index 0.
// Slide One has a transient <1> then a later <2->, so its final step (2) is past
// the transient (which is therefore hidden in the thumbnail).
const SRC =
  "!slide One\n[a transient aside]<1>, then [permanent]<2-> text\n" +
  "!slide Two\nbody two\n!slide Three\nbody three\n" +
  "!slide Four\nbody four\n!slide Five\nbody five\n!slide Six\nbody six\n";

before(async () => {
  deck = buildDeckFromSource(SRC);
  browser = await launch();
  page = await browser.newPage();
  await page.setViewport({ width: 1200, height: 700 });
  await page.goto(deck.url, { waitUntil: "load" });
  await page.evaluate(() => window.MathJax.startup.promise);
  await new Promise((r) => setTimeout(r, 300));
});

after(async () => {
  if (browser) await browser.close();
  if (deck) deck.cleanup();
});

const D = () => page.evaluate(() => document.querySelector(".deck")._lmrDeck.overview.mode);

test("'o' opens the grid: a thumbnail per slide, current one highlighted", async () => {
  await page.evaluate(() => document.querySelector(".deck")._lmrDeck.go(2, 0));
  await page.keyboard.press("o");
  await new Promise((r) => setTimeout(r, 150));
  const r = await page.evaluate(() => {
    const ov = document.querySelector(".deck-overview");
    const thumbs = [...document.querySelectorAll(".overview-thumb")];
    const cur = document.querySelector(".overview-thumb.is-current");
    return {
      isGrid: !ov.hidden && ov.classList.contains("is-grid"),
      nThumbs: thumbs.length,
      nSlides: document.querySelectorAll(".deck > .slide").length,
      curSlide: cur && cur.dataset.slide,
      scale: +getComputedStyle(ov).getPropertyValue("--thumb-scale"),
    };
  });
  assert.equal(await D(), "grid");
  assert.ok(r.isGrid, "the grid plane is shown");
  assert.equal(r.nThumbs, r.nSlides);
  assert.equal(r.curSlide, "2", "the current slide's thumb is marked");
  assert.ok(r.scale > 0 && r.scale < 1, `thumbnails are scaled down (${r.scale})`);
});

test("thumbnails show the FINAL step (transient overlays gone)", async () => {
  // slide 0's transient <1> element is hidden in its final-step thumbnail
  const hidden = await page.evaluate(() => {
    const thumb = document.querySelector('.overview-thumb[data-slide="0"]');
    const el = [...thumb.querySelectorAll("[data-when]")][0];
    return el && !el.classList.contains("is-visible");
  });
  assert.ok(hidden, "the transient element is not visible in the thumbnail");
});

test("clicking a thumbnail jumps to that slide (step 0) and closes the grid", async () => {
  await page.evaluate(() =>
    document.querySelector('.overview-thumb[data-slide="4"]').click());
  await new Promise((r) => setTimeout(r, 100));
  const r = await page.evaluate(() => {
    const d = document.querySelector(".deck")._lmrDeck;
    return { mode: d.overview.mode, i: d.i, s: d.s,
      hidden: document.querySelector(".deck-overview").hidden };
  });
  assert.deepEqual([r.mode, r.i, r.s, r.hidden], ["present", 4, 0, true]);
});

test("'O' docks the sidebar and narrows the live deck; arrows still present",
  async () => {
    const full = await page.evaluate(() =>
      +getComputedStyle(document.querySelector(".deck")).getPropertyValue("--scale"));
    await page.keyboard.down("Shift");
    await page.keyboard.press("O");
    await page.keyboard.up("Shift");
    await new Promise((r) => setTimeout(r, 150));
    const r = await page.evaluate(() => {
      const ov = document.querySelector(".deck-overview");
      const deck = document.querySelector(".deck");
      return {
        mode: document.querySelector(".deck")._lmrDeck.overview.mode,
        isSidebar: ov.classList.contains("is-sidebar"),
        docked: deck.classList.contains("is-docked"),
        deckX: Math.round(deck.getBoundingClientRect().x),
        scale: +getComputedStyle(deck).getPropertyValue("--scale"),
        // the sidebar scroll container overflows with six thumbs on a 700px page
        scrollable: (() => { const g = ov.querySelector(".deck-overview-grid");
          return g.scrollHeight > g.clientHeight; })(),
      };
    });
    assert.equal(r.mode, "sidebar");
    assert.ok(r.isSidebar && r.docked);
    assert.ok(r.deckX > 0, `the deck is shifted right of the rail (x=${r.deckX})`);
    assert.ok(r.scale < full, `the deck rescaled smaller (${r.scale} < ${full})`);
    assert.ok(r.scrollable, "the sidebar scrolls when slides exceed the height");

    // arrows keep presenting while the sidebar is docked
    const before = await page.evaluate(() => document.querySelector(".deck")._lmrDeck.i);
    await page.keyboard.press("ArrowRight");
    const after = await page.evaluate(() => document.querySelector(".deck")._lmrDeck.i);
    assert.equal(after, before + 1, "ArrowRight advanced the deck under the sidebar");
  });

test("the sidebar gutter can be dragged wider (deck rescales, width persists)",
  async () => {
    // the sidebar is still open from the previous test; drag its right edge
    const before = await page.evaluate(() => {
      const r = document.querySelector(".deck-overview-resizer").getBoundingClientRect();
      return {
        cx: Math.round(r.x + r.width / 2),
        w: parseInt(getComputedStyle(document.documentElement).getPropertyValue("--sidebar-w")),
        scale: +getComputedStyle(document.querySelector(".deck")).getPropertyValue("--scale"),
      };
    });
    // drag the handle 200px to the right
    await page.mouse.move(before.cx, 300);
    await page.mouse.down();
    await page.mouse.move(before.cx + 200, 300, { steps: 6 });
    await page.mouse.up();
    await new Promise((r) => setTimeout(r, 120));
    const after = await page.evaluate(() => ({
      w: parseInt(getComputedStyle(document.documentElement).getPropertyValue("--sidebar-w")),
      left: parseInt(getComputedStyle(document.querySelector(".deck")).left),
      scale: +getComputedStyle(document.querySelector(".deck")).getPropertyValue("--scale"),
      saved: (() => { try { return localStorage.getItem("lmr-sidebar-w"); } catch { return null; } })(),
    }));
    assert.ok(after.w > before.w + 100, `sidebar widened (${before.w} -> ${after.w})`);
    assert.equal(after.left, after.w, "the docked deck follows the new width");
    assert.ok(after.scale < before.scale, "the live slide rescaled smaller");
    assert.equal(after.saved, String(after.w), "the width is remembered (localStorage)");
    // leave the sidebar open for the next test to close via Escape
  });

test("'Escape' leaves the overview and restores the full-width deck", async () => {
  await page.keyboard.press("Escape");
  await new Promise((r) => setTimeout(r, 100));
  const r = await page.evaluate(() => ({
    mode: document.querySelector(".deck")._lmrDeck.overview.mode,
    docked: document.querySelector(".deck").classList.contains("is-docked"),
    hidden: document.querySelector(".deck-overview").hidden,
    deckX: Math.round(document.querySelector(".deck").getBoundingClientRect().x),
  }));
  assert.deepEqual([r.mode, r.docked, r.hidden, r.deckX], ["present", false, true, 0]);
});
