#!/usr/bin/env node
// Render a built lemur deck to a handout PDF via headless Chrome: one page per
// cumulative step (Plan.md Section 4.7). Math prints as selectable vector text
// and arrows as vector SVG.
//
//   node tools/pdf.mjs <deck-dir|index.html> [out.pdf]
//
// Set $CHROME if Chrome is not at /usr/bin/google-chrome-stable. This uses
// puppeteer-core against the system browser (no bundled download). The
// zero-tooling alternative is to build the deck with --print and run
//   chrome --headless --print-to-pdf=out.pdf --no-pdf-header-footer index.html
import puppeteer from "puppeteer-core";
import { pathToFileURL } from "node:url";
import { statSync } from "node:fs";
import { join, resolve } from "node:path";

const inArg = process.argv[2];
const outPdf = process.argv[3] || "deck.pdf";
if (!inArg) {
  console.error("usage: node tools/pdf.mjs <deck-dir|index.html> [out.pdf]");
  process.exit(2);
}
let indexPath = resolve(inArg);
if (statSync(indexPath).isDirectory()) indexPath = join(indexPath, "index.html");
const url = pathToFileURL(indexPath).href + "?print";
const chrome = process.env.CHROME || process.env.PUPPETEER_EXECUTABLE_PATH
  || "/usr/bin/google-chrome-stable";

const browser = await puppeteer.launch({
  executablePath: chrome, headless: true,
  args: ["--no-sandbox", "--disable-setuid-sandbox"]
});
try {
  const page = await browser.newPage();
  await page.goto(url, { waitUntil: "networkidle0" });
  await page.evaluate(() => window.MathJax && window.MathJax.startup
    ? window.MathJax.startup.promise : null);
  // build the frozen pages if the ?print eager path has not already
  await page.evaluate(() => {
    const d = document.querySelector(".deck") &&
      document.querySelector(".deck")._lmrDeck;
    if (d && !document.querySelector(".print-page")) d.buildPrintPages();
  });
  await page.waitForFunction(
    () => document.querySelectorAll(".print-page").length > 0, { timeout: 15000 });
  const pages = await page.$$eval(".print-page", (els) => els.length);
  await page.pdf({ path: outPdf, preferCSSPageSize: true, printBackground: true });
  console.log(`wrote ${outPdf} (${pages} pages)`);
} finally {
  await browser.close();
}
