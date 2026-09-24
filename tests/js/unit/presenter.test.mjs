// Step 2 proof: the presenter core is source-agnostic. It drives a plain deck
// (the .slide/.stage + data-* step protocol) with zero lemur knowledge, and all
// lemur-specific behaviour (code highlighting, annotation arrows, math) is layered
// on only when the bridge attaches via lifecycle hooks. Arrows are the acid test:
// they no longer live on the core (they draw in the puppeteer arrows.test.mjs).
import { test } from "node:test";
import assert from "node:assert/strict";
import { JSDOM } from "jsdom";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const LMR = require("../../../lemur/assets/runtime.js");
const dom = new JSDOM("<!doctype html><body></body>");
global.window = dom.window;
global.document = dom.window.document;

/** A source-neutral deck: no lemur classes, just the display contract. */
function plainDeck(inner) {
  const el = document.createElement("div");
  el.className = "deck";
  el.dataset.designW = "1920";
  el.dataset.designH = "1080";
  el.innerHTML = inner;
  return el;
}

test("the display contract is versioned (spec/display-contract.md)", () => {
  assert.equal(LMR.contractVersion, 3);
});

test("the presenter core carries no lemur (arrow/annotation) methods", () => {
  const deck = new LMR.Deck(plainDeck("<section class='slide'></section>"));
  // the arrow machinery moved out to the bridge extension
  assert.equal(deck.decorate, undefined);
  assert.equal(deck.measureArrows, undefined);
  assert.equal(deck.ensureMeasured, undefined);
  assert.equal(deck.measureAllArrows, undefined);
  // it exposes an extension surface instead
  assert.equal(typeof deck.on, "function");
  assert.equal(typeof deck.emit, "function");
  assert.equal(typeof deck.addStepCounter, "function");
  assert.equal(typeof deck.whenReady, "function");
});

test("the core step model drives a plain deck via the data-* protocol", () => {
  const el = plainDeck(
    "<section class='slide'><div class='stage'>" +
    "<p>base</p><p data-appear='1'>later</p></div></section>" +
    "<section class='slide'><div class='stage'><p>two</p></div></section>");
  const deck = new LMR.Deck(el);
  deck.recountSteps();
  assert.equal(deck.steps[0], 1);                       // one step on slide 0
  const later = el.querySelector("[data-appear='1']");
  deck.go(0, 0, true);
  assert.equal(later.classList.contains("is-visible"), false);
  deck.go(0, 1, true);
  assert.equal(later.classList.contains("is-visible"), true);   // core-only, no bridge
});

test("extensions add steps and per-step behaviour purely through hooks", () => {
  const el = plainDeck(
    "<section class='slide'><div class='stage'><p>x</p></div></section>");
  const deck = new LMR.Deck(el);
  const seen = [];
  deck.on("step", (root, s) => seen.push(s));
  deck.addStepCounter(() => 4);
  deck.recountSteps();
  assert.equal(deck.steps[0], 4, "an extension's step count is included");
  deck.go(0, 3, true);
  assert.ok(seen.includes(3), "the 'step' hook fires with the current step");
});

test("code highlighting exists only once the lemur bridge attaches", () => {
  const el = plainDeck(
    "<section class='slide'><div class='stage'><pre class='lmr-code'><code>" +
    "<span class='cl' data-line='1'>a</span>" +
    "<span class='cl' data-line='2'>b</span></code></pre></div></section>");
  el.querySelector("code").setAttribute(
    "data-highlights", JSON.stringify({ "1": ["2"] }));
  const slide = el.querySelector(".slide");
  const deck = new LMR.Deck(el);

  // core alone: a highlight group is neither a step nor painted
  deck.recountSteps();
  assert.equal(deck.steps[0], 0);
  deck.applyState(slide, 1);
  assert.equal(el.querySelector(".cl[data-line='2']").classList.contains("cl-hl"),
    false, "no code highlight without the bridge");

  // attach the lemur extensions -> the highlight becomes a step and paints
  LMR.attachLemur(deck);
  deck.recountSteps();
  assert.equal(deck.steps[0], 1, "the highlight group now adds a step");
  deck.applyState(slide, 1);
  assert.equal(el.querySelector(".cl[data-line='2']").classList.contains("cl-hl"),
    true, "highlighted line emphasised via the 'step' hook");
  assert.equal(el.querySelector(".cl[data-line='1']").classList.contains("cl-dim"),
    true, "other lines dimmed");
});

// -- slide overview (Slide Sorter grid + docked sidebar) -------------------

test("overview plugin: one thumbnail per slide, frozen at its FINAL step", () => {
  // slide 0: a transient <1> element and a cumulative <2->; final step is 2, so
  // at the frozen final variant the cumulative shows and the transient is gone
  const el = plainDeck(
    "<section class='slide center'><div class='stage'>" +
    "<p>base</p><p data-when='1'>transient</p><p data-appear='2'>final</p>" +
    "</div></section>" +
    "<section class='slide'><div class='stage'><p>two</p></div></section>");
  const deck = new LMR.Deck(el);
  deck.recountSteps();
  assert.equal(deck.steps[0], 2);
  const ov = LMR.createOverview(deck);   // attach the overview plugin to the core
  const plane = ov.build();
  assert.equal(plane.className, "deck-overview");
  const thumbs = [...plane.querySelectorAll(".overview-thumb")];
  assert.equal(thumbs.length, 2);
  const p = (t, txt) => [...t.querySelectorAll("p")].find((e) => e.textContent === txt);
  assert.ok(p(thumbs[0], "final").classList.contains("is-visible"), "cumulative shown");
  assert.ok(!p(thumbs[0], "transient").classList.contains("is-visible"), "transient gone");
  // the frozen page carries the slide's variant classes, not 'slide'/is-*
  assert.ok(thumbs[0].classList.contains("center"));
  assert.ok(!thumbs[0].classList.contains("slide"));
  assert.equal(thumbs[0].dataset.slide, "0");
  assert.equal(ov.build(), plane, "built once, cached");
});

test("overview plugin modes toggle: present <-> grid <-> sidebar", () => {
  const el = plainDeck(
    "<section class='slide'><div class='stage'><p>a</p></div></section>" +
    "<section class='slide'><div class='stage'><p>b</p></div></section>");
  const deck = new LMR.Deck(el);
  deck.recountSteps();
  const ov = LMR.createOverview(deck);
  const plane = ov.build();                    // this deck's plane (body is shared)
  assert.equal(ov.mode, "present");
  ov.toggle("grid");
  assert.equal(ov.mode, "grid");
  assert.ok(!plane.hidden && plane.classList.contains("is-grid"));
  assert.ok(el.classList.contains("is-gridded"));
  ov.toggle("sidebar");                        // switch grid -> sidebar
  assert.equal(ov.mode, "sidebar");
  assert.ok(plane.classList.contains("is-sidebar") && !plane.classList.contains("is-grid"));
  assert.ok(el.classList.contains("is-docked") && !el.classList.contains("is-gridded"));
  ov.toggle("sidebar");                        // toggle off -> present
  assert.equal(ov.mode, "present");
  assert.ok(plane.hidden);
  assert.ok(!el.classList.contains("is-docked"));
  // the core stays overview-agnostic: it exposes the levers the plugin drives
  assert.equal(deck.wheelNav, true);
  assert.equal(deck.viewportInset, 0);
});
