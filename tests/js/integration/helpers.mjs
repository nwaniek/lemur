// Shared helpers for the headless-browser integration tests.
// Builds a deck with lemur.emit.slides and drives it with puppeteer-core against the
// system Chrome (no bundled-browser download).
import { execFileSync } from "node:child_process";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, dirname, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import puppeteer from "puppeteer-core";

const HERE = dirname(fileURLToPath(import.meta.url));
// tests/js/integration -> tests/js -> tests -> repo root
export const REPO = resolve(HERE, "..", "..", "..");

export function chromePath() {
  return process.env.CHROME
    || process.env.PUPPETEER_EXECUTABLE_PATH
    || "/usr/bin/google-chrome-stable";
}

/** Build a deck folder from a master .lmr with the deck builder. Returns its
 *  path and a cleanup(). extraArgs is an array of extra CLI flags (e.g.
 *  ["--theme", "dark"]). */
// The deck is built AST-driven: the parser (lemur.parser) turns .lmr into the
// neutral AST and the deck builder (lemur.emit.slides, run as `python3 -m lemur.emit.slides`
// from the repo root) packages it (thin shell embeds the AST; runtime.js renders it).
export function buildDeck(masterRelPath, extraArgs = []) {
  const out = mkdtempSync(join(tmpdir(), "lemur-deck-"));
  execFileSync("python3",
    ["-m", "lemur.emit.slides", join(REPO, masterRelPath), "-o", out, ...extraArgs],
    { stdio: "pipe", cwd: REPO });
  return {
    dir: out,
    url: pathToFileURL(join(out, "index.html")).href,
    cleanup: () => rmSync(out, { recursive: true, force: true })
  };
}

/** Build a deck from inline lemur source (written to a temp master.lmr). */
export function buildDeckFromSource(lmr, extraArgs = []) {
  const src = mkdtempSync(join(tmpdir(), "lemur-src-"));
  const out = mkdtempSync(join(tmpdir(), "lemur-deck-"));
  const master = join(src, "master.lmr");
  writeFileSync(master, lmr);
  execFileSync("python3",
    ["-m", "lemur.emit.slides", master, "-o", out, ...extraArgs],
    { stdio: "pipe", cwd: REPO });
  return {
    dir: out,
    url: pathToFileURL(join(out, "index.html")).href,
    cleanup: () => { rmSync(out, { recursive: true, force: true });
      rmSync(src, { recursive: true, force: true }); }
  };
}

export async function launch() {
  return puppeteer.launch({
    executablePath: chromePath(),
    headless: true,
    args: ["--no-sandbox", "--disable-setuid-sandbox", "--font-render-hinting=none"]
  });
}

/** Index of the single .is-current slide (or -1). */
export const CURRENT_INDEX = `(() => {
  const slides = Array.from(document.querySelectorAll('.deck > .slide'));
  return slides.findIndex(s => s.classList.contains('is-current'));
})()`;
