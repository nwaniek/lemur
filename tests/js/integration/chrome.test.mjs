// Items 2 + 3: navigation wedges and presentation chrome (header/footer/slide
// number).
import { test, before, after } from "node:test";
import assert from "node:assert/strict";
import { buildDeck, buildDeckFromSource, launch, CURRENT_INDEX } from "./helpers.mjs";

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

test("the cover has no footer or slide number; content slides do", async () => {
  const res = await page.evaluate(() => {
    const slides = [...document.querySelectorAll(".deck > .slide")];
    const cover = slides[0];
    const content = slides.find((s) => !s.classList.contains("cover"));
    return {
      coverHasFooter: !!cover.querySelector(".lmr-footer"),
      contentPageno: content.querySelector(".lmr-pageno")
        ? content.querySelector(".lmr-pageno").textContent : null,
      contentFooterText: content.querySelector(".lmr-footer-text")
        ? content.querySelector(".lmr-footer-text").textContent : null,
      nonCover: slides.filter((s) => !s.classList.contains("cover")).length
    };
  });
  assert.equal(res.coverHasFooter, false);
  // n / N where N is the number of non-cover slides (resolved live)
  assert.match(res.contentPageno, new RegExp("^\\d+ / " + res.nonCover + "$"));
  assert.equal(res.contentFooterText, "Message Passing on Graphs"); // title
});

test("nav wedges step the deck and dim at the ends", async () => {
  await page.goto(deck.url + "#/0/0", { waitUntil: "load" });
  // at the very start, Prev is disabled (pointer-events:none via .at-start)
  let nav = await page.evaluate(() => ({
    atStart: document.querySelector(".deck-nav").classList.contains("at-start"),
    atEnd: document.querySelector(".deck-nav").classList.contains("at-end")
  }));
  assert.ok(nav.atStart && !nav.atEnd);

  // clicking Next advances the current slide
  await page.click(".deck-nav-next");
  assert.equal(await page.evaluate(CURRENT_INDEX), 1);
  await page.click(".deck-nav-prev");
  assert.equal(await page.evaluate(CURRENT_INDEX), 0);

  // at the very end, Next is disabled
  await page.keyboard.press("End");
  nav = await page.evaluate(() =>
    document.querySelector(".deck-nav").classList.contains("at-end"));
  assert.ok(nav);
});

test("Next is cued differently for a within-slide reveal vs a slide change",
  async () => {
    // slide 4 (Definition) has steps; at step 0 there is more to uncover
    await page.goto(deck.url + "#/4/0", { waitUntil: "load" });
    assert.equal(await page.evaluate(
      () => document.querySelector(".deck-nav").dataset.more), "step");
    // at its last step, Next will move to the next slide
    await page.goto(deck.url + "#/4/3", { waitUntil: "load" });
    assert.equal(await page.evaluate(
      () => document.querySelector(".deck-nav").dataset.more), "slide");
  });

test("header/footer and slide numbers are configurable", async () => {
  const d = buildDeckFromSource(
    "!title T\n!header My Section\n!footer Custom Footer\n" +
    "!slide One\nx\n!slide Two\ny\n");
  const p = await browser.newPage();
  await p.goto(d.url + "#/1/0", { waitUntil: "load" });  // content slide "One"
  const res = await p.evaluate(() => {
    const s = document.querySelector(".slide.is-current");
    return {
      header: s.querySelector(".lmr-header") ? s.querySelector(".lmr-header").textContent : null,
      footer: s.querySelector(".lmr-footer-text").textContent,
      pageno: s.querySelector(".lmr-pageno").textContent
    };
  });
  assert.equal(res.header, "My Section");
  assert.equal(res.footer, "Custom Footer");
  assert.equal(res.pageno, "1 / 2");
  await p.close();
  d.cleanup();

  // slidenumbers off removes the number
  const d2 = buildDeckFromSource(
    "!slidenumbers off\n!slide One\nx\n");
  const p2 = await browser.newPage();
  await p2.goto(d2.url, { waitUntil: "load" });
  const hasNo = await p2.evaluate(() =>
    !!document.querySelector(".slide.is-current .lmr-pageno"));
  assert.equal(hasNo, false);
  await p2.close();
  d2.cleanup();
});
