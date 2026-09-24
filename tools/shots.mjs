#!/usr/bin/env node
// Capture one screenshot per (slide, step) of a built deck for manual visual
// review. Not a test (no committed baselines) — a human-in-the-loop aid.
//
//   node tools/shots.mjs <deck-dir|index.html> [out-dir]
//
// Set $CHROME if Chrome is not at /usr/bin/google-chrome-stable.
import puppeteer from "puppeteer-core";
import { pathToFileURL } from "node:url";
import { statSync, mkdirSync } from "node:fs";
import { join, resolve } from "node:path";

const inArg = process.argv[2];
const outDir = process.argv[3] || "shots";
if (!inArg) {
  console.error("usage: node tools/shots.mjs <deck-dir|index.html> [out-dir]");
  process.exit(2);
}
let indexPath = resolve(inArg);
if (statSync(indexPath).isDirectory()) indexPath = join(indexPath, "index.html");
mkdirSync(outDir, { recursive: true });
const base = pathToFileURL(indexPath).href;
const chrome = process.env.CHROME || "/usr/bin/google-chrome-stable";

const browser = await puppeteer.launch({
  executablePath: chrome, headless: true,
  args: ["--no-sandbox", "--disable-setuid-sandbox"]
});
try {
  const page = await browser.newPage();
  await page.setViewport({ width: 1600, height: 900 });
  await page.goto(base, { waitUntil: "networkidle0" });
  await page.evaluate(() => window.MathJax && window.MathJax.startup
    ? window.MathJax.startup.promise : null);
  const steps = await page.evaluate(
    () => document.querySelector(".deck")._lmrDeck.steps);
  let n = 0;
  for (let i = 0; i < steps.length; i++) {
    for (let k = 0; k <= steps[i]; k++) {
      await page.goto(base + `#/${i}/${k}`, { waitUntil: "load" });
      await new Promise((r) => setTimeout(r, 200));
      const name = `slide${String(i).padStart(2, "0")}-step${k}.png`;
      await page.screenshot({ path: join(outDir, name) });
      n++;
    }
  }
  console.log(`wrote ${n} screenshots to ${outDir}/`);
} finally {
  await browser.close();
}
