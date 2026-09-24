// Unit tests for the pure functions of lemur/assets/runtime.js (Plan.md Section 5).
// These need no DOM, so they run under plain node:test.
import { test } from "node:test";
import assert from "node:assert/strict";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const LMR = require("../../../lemur/assets/runtime.js");

test("computeScale fits the design box and never stretches", () => {
  // exact 16:9 match -> integer-ish scale
  assert.equal(LMR.computeScale(1280, 720, 1280, 720), 1);
  assert.equal(LMR.computeScale(2560, 1440, 1280, 720), 2);
  // wider viewport than design: height is the limiting dimension
  assert.equal(LMR.computeScale(3000, 720, 1280, 720), 1);
  // taller viewport than design: width limits
  assert.equal(LMR.computeScale(1280, 2000, 1280, 720), 1);
  // uniform: min of the two ratios
  assert.equal(LMR.computeScale(640, 720, 1280, 720), 0.5);
});

test("computeScale guards a degenerate design box", () => {
  assert.equal(LMR.computeScale(800, 600, 0, 720), 1);
  assert.equal(LMR.computeScale(800, 600, 1280, 0), 1);
});

test("parseHash reads '#/<slide>/<step>' tolerantly", () => {
  assert.deepEqual(LMR.parseHash("#/3/2"), { slide: 3, step: 2 });
  assert.deepEqual(LMR.parseHash("#/5"), { slide: 5, step: 0 });
  assert.deepEqual(LMR.parseHash("/1/4"), { slide: 1, step: 4 });
  assert.equal(LMR.parseHash(""), null);
  assert.equal(LMR.parseHash("#garbage"), null);
  assert.equal(LMR.parseHash(undefined), null);
});

test("formatHash round-trips with parseHash", () => {
  assert.equal(LMR.formatHash(3, 2), "#/3/2");
  assert.equal(LMR.formatHash(0, 0), "#/0/0");
  const h = LMR.formatHash(7, 4);
  assert.deepEqual(LMR.parseHash(h), { slide: 7, step: 4 });
});

test("clampLocation clamps slide and step into range", () => {
  const deck = { steps: [0, 3, 1] }; // 3 slides with S = 0, 3, 1
  assert.deepEqual(LMR.clampLocation(1, 2, deck), { slide: 1, step: 2 });
  // step beyond S is clamped to S
  assert.deepEqual(LMR.clampLocation(1, 99, deck), { slide: 1, step: 3 });
  // slide beyond the last is clamped, and step re-clamped to that slide's S
  assert.deepEqual(LMR.clampLocation(99, 99, deck), { slide: 2, step: 1 });
  // negatives / NaN fall back to 0
  assert.deepEqual(LMR.clampLocation(-1, -5, deck), { slide: 0, step: 0 });
  assert.deepEqual(LMR.clampLocation(NaN, NaN, deck), { slide: 0, step: 0 });
});

test("clampLocation on an empty deck is (0,0)", () => {
  assert.deepEqual(LMR.clampLocation(3, 3, { steps: [] }), { slide: 0, step: 0 });
  assert.deepEqual(LMR.clampLocation(3, 3, {}), { slide: 0, step: 0 });
});

test("stepInSpec implements overlay specs (only / from / to / range)", () => {
  const inSpec = LMR.stepInSpec;
  // "n" — only step n (transient)
  assert.equal(inSpec("3", 3), true);
  assert.equal(inSpec("3", 2), false);
  assert.equal(inSpec("3", 4), false);
  // "n-" — from n onward
  assert.equal(inSpec("2-", 1), false);
  assert.equal(inSpec("2-", 2), true);
  assert.equal(inSpec("2-", 9), true);
  // "-n" — up to n
  assert.equal(inSpec("-3", 3), true);
  assert.equal(inSpec("-3", 4), false);
  // "n-m" — range, hides after
  assert.deepEqual([0, 1, 2, 3, 4].map((s) => inSpec("2-3", s)),
    [false, false, true, true, false]);
  // comma list
  assert.deepEqual([1, 2, 3, 4].map((s) => inSpec("1,3", s)),
    [true, false, true, false]);
});

test("toDesignCoords undoes stage offset and scale", () => {
  const stageRect = { left: 100, top: 50, width: 640, height: 360 };
  // a rect at stage-local (200,100) size 40x20 under scale 0.5 appears on
  // screen at (100+200*0.5, 50+100*0.5) = (200,100), size 20x10
  const rect = { left: 200, top: 100, width: 20, height: 10 };
  const d = LMR.toDesignCoords(rect, stageRect, 0.5);
  assert.deepEqual(d, { x: 200, y: 100, w: 40, h: 20 });
});

test("toDesignCoords at scale 1 is a pure translation (print path)", () => {
  const stageRect = { left: 0, top: 0, width: 1280, height: 720 };
  const rect = { left: 300, top: 150, width: 40, height: 20 };
  assert.deepEqual(LMR.toDesignCoords(rect, stageRect, 1),
    { x: 300, y: 150, w: 40, h: 20 });
});

test("arrowEndpoints: callout below the target points up at its centre", () => {
  const callout = { x: 100, y: 200, w: 80, h: 30 };
  const target = { x: 120, y: 100, w: 40, h: 20 };  // centre x = 140
  const ep = LMR.arrowEndpoints(callout, target, { standoff: 6 });
  assert.equal(ep.x1, 140);              // ends at the target centre x
  assert.equal(ep.y1, 100 + 20 + 6);     // a standoff below the target bottom
  assert.equal(ep.y0, 200);              // starts on the callout's top edge
  assert.equal(ep.x0, 140);              // and near the target's x
  // control points keep the curve vertical (same x as their endpoints)
  assert.equal(ep.c1x, ep.x0);
  assert.equal(ep.c2x, ep.x1);
});

test("arrowEndpoints: callout above the target points down", () => {
  const callout = { x: 100, y: 0, w: 80, h: 30 };
  const target = { x: 120, y: 100, w: 40, h: 20 };
  const ep = LMR.arrowEndpoints(callout, target, { standoff: 6 });
  assert.equal(ep.y0, 30);               // callout bottom edge
  assert.equal(ep.y1, 100 - 6);          // standoff above the target top
});

test("arrowEndpoints: start x is clamped to the callout's own edges", () => {
  // target far to the right of a narrow callout: the line still starts on the
  // callout box, not floating out at the target's x
  const callout = { x: 100, y: 200, w: 40, h: 20 };
  const target = { x: 900, y: 100, w: 30, h: 20 };
  const ep = LMR.arrowEndpoints(callout, target);
  assert.ok(ep.x0 <= callout.x + callout.w && ep.x0 >= callout.x);
  assert.equal(ep.x1, 915);              // end still aims at the target centre
});
