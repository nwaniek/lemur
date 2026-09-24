// M5 integration test: the frozen print build has one page per cumulative
// step, no reveal markers, correct per-page coloring, and yields a PDF
// (Plan.md Section 4.7, acceptance 5/6).
import { test, before, after } from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, rmSync, statSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { buildDeck, launch } from "./helpers.mjs";

let deck, browser, page, outdir;

before(async () => {
  deck = buildDeck("example/master.lmr", ["--print"]);
  browser = await launch();
  page = await browser.newPage();
  await page.setViewport({ width: 1600, height: 900 });
  await page.goto(deck.url + "?print", { waitUntil: "networkidle0" });
  await page.evaluate(() => window.MathJax.startup.promise);
  await page.waitForFunction(
    () => document.querySelectorAll(".print-page").length > 0, { timeout: 15000 });
  outdir = mkdtempSync(join(tmpdir(), "lemur-pdf-"));
});

after(async () => {
  if (browser) await browser.close();
  if (deck) deck.cleanup();
  if (outdir) rmSync(outdir, { recursive: true, force: true });
});

test("one print page per cumulative step across the deck", async () => {
  const { pages, expected, perSlide } = await page.evaluate(() => {
    const d = document.querySelector(".deck")._lmrDeck;
    const expected = d.steps.reduce((n, s) => n + s + 1, 0);
    return {
      pages: document.querySelectorAll(".print-page").length,
      expected,
      perSlide: d.steps.map((s) => s + 1)
    };
  });
  assert.equal(pages, expected);          // one page per cumulative step
  assert.ok(pages >= 30, `sanity lower bound (got ${pages})`);
  // every slide contributes at least one page (step 0)
  assert.ok(perSlide.every((n) => n >= 1) && perSlide.length >= 13);
});

test("building print pages does not disturb the on-screen slide", async () => {
  // loaded at ?print (eager build already ran); the interactive deck must be
  // untouched — this is what caused the print-dialog flicker before the fix
  const current = () => page.evaluate(() => Array.from(
    document.querySelectorAll(".deck > .slide"))
    .findIndex((s) => s.classList.contains("is-current")));
  assert.equal(await current(), 0);
  await page.evaluate(() => window.dispatchEvent(new Event("beforeprint")));
  assert.equal(await current(), 0);       // a rebuild leaves it in place
});

test("print pages carry no reveal markers", async () => {
  const dirty = await page.$$eval(".print-root .reveal, .print-root .fragment, "
    + ".print-root .r-stack", (els) => els.length);
  assert.equal(dirty, 0);
});

test("a mid-step frozen page shows exactly the coloring for that step",
  async () => {
    // find the sum-product pages and check step 2 (prod only) vs step 4 (all)
    const res = await page.evaluate(() => {
      const pages = [...document.querySelectorAll(".print-page")];
      const sp = pages.filter((p) => (p.querySelector("h2") || {}).textContent
        === "The sum-product update");
      const hlSet = (p) => ["sum", "fac", "prod"].filter((n) =>
        p.querySelector(".lmr-a-" + n) &&
        p.querySelector(".lmr-a-" + n).classList.contains("is-hl"));
      // sp[0]=step0 ... sp[2]=step2, sp[4]=step4
      return { step2: hlSet(sp[2]), step4: hlSet(sp[4]) };
    });
    assert.deepEqual(res.step2.sort(), ["prod"]);
    assert.deepEqual(res.step4.sort(), ["fac", "prod", "sum"]);
  });

test("frozen pages carry the slide's variant classes; connectors gate per step",
  async () => {
    // regression: the print clone is only the .stage, so the page must carry the
    // slide's variant/kind classes or .center/.middle/plain CSS (and the layout
    // the arrows were measured against) would not apply on print
    const res = await page.evaluate(() => {
      const pages = [...document.querySelectorAll(".print-page")];
      const of = (title) => pages.filter((p) =>
        (p.querySelector("h2") || {}).textContent === title);
      const conn = of("What is our field about?");
      const cls = conn.length ? [...conn[0].classList] : null;
      const arrowsVisible = (p) => [...p.querySelectorAll("g.arrow")]
        .filter((g) => g.classList.contains("is-visible")).length;
      return {
        cls,
        // step 0 = no connector visible; step 2 = both visible (cumulative)
        step0Visible: conn.length ? arrowsVisible(conn[0]) : -1,
        step2Visible: conn.length >= 3 ? arrowsVisible(conn[2]) : -1,
      };
    });
    assert.ok(res.cls, "connector slide print pages found");
    assert.ok(res.cls.includes("center") && res.cls.includes("middle"),
      `page carries alignment classes (got ${res.cls})`);
    assert.ok(!res.cls.includes("slide") && !res.cls.some((c) => c.startsWith("is-")),
      "but not 'slide' or transient is-* state");
    assert.equal(res.step0Visible, 0, "no connector arrow on step 0");
    assert.equal(res.step2Visible, 2, "both connector arrows on step 2");
  });

test("page.pdf() produces a non-trivial PDF", async () => {
  const out = join(outdir, "deck.pdf");
  await page.pdf({ path: out, preferCSSPageSize: true, printBackground: true });
  assert.ok(statSync(out).size > 20000, "PDF is written and non-trivial");
});
