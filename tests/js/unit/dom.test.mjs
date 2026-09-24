// Unit tests for the DOM-touching pure functions of runtime.js under jsdom:
// slideStepCount and applyStep (the activation model, Plan.md Section 4.3).
import { test } from "node:test";
import assert from "node:assert/strict";
import { JSDOM } from "jsdom";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const LMR = require("../../../lemur/assets/runtime.js");

/** Build a .slide element from inner HTML. */
function slide(html) {
  const dom = new JSDOM(`<section class="slide">${html}</section>`);
  return dom.window.document.querySelector(".slide");
}
const vis = (el) => el.classList.contains("is-visible");
const hl = (el) => el.classList.contains("is-hl");

test("slideStepCount is 0 for a slide with no activation", () => {
  const s = slide("<p>plain</p>");
  assert.equal(LMR.slideStepCount(s), 0);
});

test("applyStep on an S=0 slide only records the step", () => {
  const s = slide("<p>plain</p>");
  LMR.applyStep(s, 0);
  assert.equal(s.dataset.step, "0");
});

test("slideStepCount is the max of data-appear and data-hl", () => {
  const s = slide(
    '<span data-appear="1">a</span><span data-hl="3">b</span>' +
    '<span data-appear="2">c</span>');
  assert.equal(LMR.slideStepCount(s), 3);
});

test("data-appear reveals at its step, forward and backward", () => {
  const s = slide('<span id="x" data-appear="1">x</span>');
  const x = s.querySelector("#x");
  LMR.applyStep(s, 0);
  assert.equal(vis(x), false);
  LMR.applyStep(s, 1);
  assert.equal(vis(x), true);
  LMR.applyStep(s, 0); // stepping back hides it again
  assert.equal(vis(x), false);
});

test("multiple data-appear elements reveal cumulatively", () => {
  const s = slide(
    '<span id="a" data-appear="1">a</span>' +
    '<span id="b" data-appear="2">b</span>' +
    '<span id="c" data-appear="3">c</span>');
  const [a, b, c] = ["#a", "#b", "#c"].map((q) => s.querySelector(q));
  LMR.applyStep(s, 2);
  assert.deepEqual([vis(a), vis(b), vis(c)], [true, true, false]);
  LMR.applyStep(s, 3);
  assert.deepEqual([vis(a), vis(b), vis(c)], [true, true, true]);
  LMR.applyStep(s, 1);
  assert.deepEqual([vis(a), vis(b), vis(c)], [true, false, false]);
});

test("data-hl accumulates and is removed on stepping back", () => {
  const s = slide(
    '<span id="p" data-hl="1">p</span><span id="q" data-hl="2">q</span>');
  const [p, q] = ["#p", "#q"].map((x) => s.querySelector(x));
  LMR.applyStep(s, 1);
  assert.deepEqual([hl(p), hl(q)], [true, false]);
  LMR.applyStep(s, 2); // cumulative: p stays highlighted, q joins
  assert.deepEqual([hl(p), hl(q)], [true, true]);
  LMR.applyStep(s, 0);
  assert.deepEqual([hl(p), hl(q)], [false, false]);
});

test("an element may carry both data-appear and data-hl independently", () => {
  const s = slide('<span id="e" data-appear="1" data-hl="2">e</span>');
  const e = s.querySelector("#e");
  LMR.applyStep(s, 1);
  assert.deepEqual([vis(e), hl(e)], [true, false]);
  LMR.applyStep(s, 2);
  assert.deepEqual([vis(e), hl(e)], [true, true]);
});

test("data-when shows only while the step matches (transient overlays)", () => {
  const s = slide(
    '<div id="from" data-when="2-">a</div>' +
    '<div id="only" data-when="3">b</div>' +
    '<div id="range" data-when="2-3">c</div>');
  const v = (id) => s.querySelector("#" + id).classList.contains("is-visible");
  LMR.applyStep(s, 1);
  assert.deepEqual([v("from"), v("only"), v("range")], [false, false, false]);
  LMR.applyStep(s, 2);
  assert.deepEqual([v("from"), v("only"), v("range")], [true, false, true]);
  LMR.applyStep(s, 3);
  assert.deepEqual([v("from"), v("only"), v("range")], [true, true, true]);
  LMR.applyStep(s, 4);   // the transient/range ones hide again
  assert.deepEqual([v("from"), v("only"), v("range")], [true, false, false]);
});

test("slideStepCount counts the max step in overlay specs", () => {
  const s = slide('<p data-when="2-5">x</p><p data-appear="1">y</p>');
  assert.equal(LMR.slideStepCount(s), 5);
});

test("freezeStage(k) matches a live applyStep(k) — one activation path", () => {
  // guards against the print build drifting from the on-screen build
  // (Plan.md Section 4.7): the frozen page for step k must be the stage after
  // applyStep(k), by construction.
  const html =
    '<div data-appear="1">a</div><span data-hl="2">b</span>' +
    '<p data-appear="2" data-hl="1">c</p>';
  const sig = (root) => Array.prototype.map.call(
    root.querySelectorAll("*"), (e) =>
      (e.classList.contains("is-visible") ? "V" : "") +
      (e.classList.contains("is-hl") ? "H" : "")).join(",");
  for (const k of [0, 1, 2, 3]) {
    const live = slide(html);
    LMR.applyStep(live, k);
    const frozen = LMR.freezeStage(slide(html), k);
    assert.equal(sig(frozen), sig(live), "step " + k);
    assert.equal(frozen.dataset.step, String(k));
  }
});
