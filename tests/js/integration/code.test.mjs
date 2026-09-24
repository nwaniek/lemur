// Items 5 + 6: stepwise code line-highlighting and highlight.js colorization.
import { test, before, after } from "node:test";
import assert from "node:assert/strict";
import { buildDeckFromSource, launch } from "./helpers.mjs";

let browser;
before(async () => { browser = await launch(); });
after(async () => { if (browser) await browser.close(); });

const CODE =
  "!slide Code\n:: python[1|3-4|2]\n" +
  "\tdef f(x):\n\ty = x + 1\n\tz = y * 2\n\treturn z\n";

test("code is syntax-colorized by highlight.js", async () => {
  const deck = buildDeckFromSource(CODE);
  const page = await browser.newPage();
  await page.goto(deck.url, { waitUntil: "networkidle0" });
  await new Promise((r) => setTimeout(r, 400)); // let hljs run
  const tokens = await page.evaluate(() =>
    document.querySelectorAll(".slide.is-current code .hljs-keyword, "
      + ".slide.is-current code .hljs-title").length);
  assert.ok(tokens >= 2, "keyword/function tokens are colorized");
  await page.close();
  deck.cleanup();
});

test("line-highlight groups step through, highlighting and dimming", async () => {
  const deck = buildDeckFromSource(CODE); // groups: [1], [3,4], [2]
  const page = await browser.newPage();
  await page.goto(deck.url, { waitUntil: "networkidle0" });
  await new Promise((r) => setTimeout(r, 300));
  const state = () => page.evaluate(() => {
    const code = document.querySelector(".slide.is-current code");
    return {
      hl: [...code.querySelectorAll(".cl.cl-hl")].map((l) => l.dataset.line),
      dim: [...code.querySelectorAll(".cl.cl-dim")].map((l) => l.dataset.line)
    };
  });
  // step 0: nothing highlighted
  await page.goto(deck.url + "#/0/0", { waitUntil: "load" });
  assert.deepEqual((await state()).hl, []);
  // step 1: line 1
  await page.goto(deck.url + "#/0/1", { waitUntil: "load" });
  let s = await state();
  assert.deepEqual(s.hl, ["1"]);
  assert.deepEqual(s.dim.sort(), ["2", "3", "4"]);
  // step 2: lines 3,4 (current group replaces, not cumulative)
  await page.goto(deck.url + "#/0/2", { waitUntil: "load" });
  assert.deepEqual((await state()).hl.sort(), ["3", "4"]);
  // step 3: line 2
  await page.goto(deck.url + "#/0/3", { waitUntil: "load" });
  assert.deepEqual((await state()).hl, ["2"]);
  await page.close();
  deck.cleanup();
});

test("highlight.js is not loaded when a deck has no code", async () => {
  const deck = buildDeckFromSource("!slide A\njust text, no code\n");
  const page = await browser.newPage();
  await page.goto(deck.url, { waitUntil: "networkidle0" });
  const html = await page.content();
  assert.ok(!/highlight\.min\.js/.test(html), "no hljs script tag");
  await page.close();
  deck.cleanup();
});
