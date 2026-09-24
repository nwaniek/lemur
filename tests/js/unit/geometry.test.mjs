// Unit tests for the runtime's arrow geometry helpers (still in runtime.js —
// arrows are measured/drawn in the browser). The AST->DOM render engine moved to
// lemur.emit.html (tested in tests/test_lemur.emit.html); these two are behavior.
import { test } from "node:test";
import assert from "node:assert/strict";
import { JSDOM } from "jsdom";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const LMR = require("../../../lemur/assets/runtime.js");
const dom = new JSDOM("<!doctype html><body></body>");
global.window = dom.window;
global.document = dom.window.document;

test("connectEndpoints attaches on the facing edges by dominant axis", () => {
  // horizontal-dominant: from's right edge -> to's left edge (minus standoff)
  const h = LMR.connectEndpoints({ x: 0, y: 0, w: 100, h: 20 },
    { x: 300, y: 0, w: 100, h: 20 }, { standoff: 6 });
  assert.equal(h.x0, 100);            // from right edge
  assert.equal(h.x1, 294);           // to left edge - standoff
  assert.equal(h.y0, 10); assert.equal(h.y1, 10);
  // vertical-dominant: from's bottom edge -> to's top edge (minus standoff)
  const v = LMR.connectEndpoints({ x: 0, y: 0, w: 100, h: 20 },
    { x: 0, y: 300, w: 100, h: 20 }, { standoff: 6 });
  assert.equal(v.y0, 20);            // from bottom edge
  assert.equal(v.y1, 294);          // to top edge - standoff
});

test("drawArrow builds a <g class=arrow> with markers per direction", () => {
  const SVGNS = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(SVGNS, "svg");
  const ep = { x0: 0, y0: 0, x1: 10, y1: 10, c1x: 5, c1y: 0, c2x: 5, c2y: 10 };
  const gf = LMR.drawArrow(svg, ep, { dir: "fwd", appear: "1", to: "lmr-a-x" });
  assert.equal(gf.getAttribute("class"), "arrow");
  assert.equal(gf.getAttribute("data-to"), "lmr-a-x");
  assert.equal(gf.querySelector("path").getAttribute("marker-end"), "url(#lmr-arrowhead)");
  assert.equal(gf.querySelector("path").getAttribute("marker-start"), null);
  const gb = LMR.drawArrow(svg, ep, { dir: "both", styles: ["dashed"] });
  assert.match(gb.getAttribute("class"), /arrow arrow-dashed/);
  assert.ok(gb.querySelector("path").getAttribute("marker-start"));
  assert.ok(gb.querySelector("path").getAttribute("marker-end"));
  const gn = LMR.drawArrow(svg, ep, { dir: "none" });
  assert.equal(gn.querySelector("path").getAttribute("marker-end"), null);
  assert.equal(gn.querySelector("path").getAttribute("marker-start"), null);
});
