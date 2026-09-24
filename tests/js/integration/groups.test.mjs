// Mark groups: reusing a mark name on a slide groups the occurrences. They share
// one colour, and one annotation label's arrow fans out to each; '!connect' pairs
// each occurrence of the larger group with its nearest counterpart. The AST is
// unchanged (marks:[{name,from,to}] already permits repeats) — grouping is a
// runtime/emitter reading. See lemur.parser extract_marks + runtime measureArrows.
import { test, before, after } from "node:test";
import assert from "node:assert/strict";
import { buildDeckFromSource, launch } from "./helpers.mjs";

let deck, browser, page;

// slide 0: prior + likelihood each appear twice (compact then expanded); one
// annotate line per name. slide 1: 'q' twice, 'ans' once, connected q -> ans.
const SRC =
  "!slide Groups\n" +
  ":: math\n" +
  "\tp(w) = \\mk{prior}{a}\\,\\mk{lik}{b} = \\mk{prior}{c} \\cdots \\mk{lik}{d}\n" +
  "\n" +
  "!annotate\n" +
  "\tprior[#7a4b94]: the prior\n" +
  "\tlik[#2b7a3d]: the likelihood\n" +
  "!slide Connect\n" +
  ":: math\n" +
  "\t\\mk{q}{Q} \\quad \\mk{q}{Q'} \\quad \\mk{ans}{A}\n" +
  "\n" +
  "!connect\n" +
  "\tq -> ans\n";

before(async () => {
  deck = buildDeckFromSource(SRC);
  browser = await launch();
  page = await browser.newPage();
  await page.setViewport({ width: 1400, height: 900 });
});

after(async () => {
  if (browser) await browser.close();
  if (deck) deck.cleanup();
});

const arrowsTo = (cls) => page.evaluate((c) => document.querySelectorAll(
  `.slide.is-current svg.arrow-layer g.arrow[data-to="${c}"]`).length, cls);

test("one annotation label fans an arrow out to each occurrence of its group",
  async () => {
    await page.goto(deck.url + "#/0/2", { waitUntil: "load" });   // final step
    await page.evaluate(() => window.MathJax.startup.promise);
    await page.waitForFunction(() =>
      document.querySelectorAll(".slide.is-current svg.arrow-layer g.arrow")
        .length >= 4);
    assert.equal(await arrowsTo("lmr-a-prior"), 2, "prior -> both occurrences");
    assert.equal(await arrowsTo("lmr-a-lik"), 2, "lik -> both occurrences");
  });

test("both occurrences of a grouped mark are coloured, and share the colour",
  async () => {
    const r = await page.evaluate(() => {
      const els = [...document.querySelectorAll(".slide.is-current .lmr-a-prior")];
      return {
        n: els.length,
        hl: els.map((e) => e.classList.contains("is-hl")),
        col: els.map((e) => getComputedStyle(e).getPropertyValue("--hl").trim()),
      };
    });
    assert.equal(r.n, 2, "two prior occurrences");
    assert.deepEqual(r.hl, [true, true], "both highlighted at the final step");
    assert.deepEqual(r.col, ["#7a4b94", "#7a4b94"], "both carry the label's colour");
  });

test("'!connect' covers each occurrence of the larger group (q x2 -> ans)",
  async () => {
    await page.goto(deck.url + "#/1/1", { waitUntil: "load" });
    await page.evaluate(() => window.MathJax.startup.promise);
    await page.waitForFunction(() =>
      document.querySelectorAll(".slide.is-current svg.arrow-layer g.arrow")
        .length >= 2);
    // q occurs twice, ans once -> two connectors, each from a q to ans
    assert.equal(await arrowsTo("lmr-a-ans"), 2, "one connector per q, both to ans");
  });
