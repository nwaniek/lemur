"""Build-time typesetting: text and maths to vector outlines.

Everything here turns a string into a list of cubic-Bézier subpaths, so the
slide emitter can bake glyphs into SVG at build time — no web fonts, no MathJax
at display time. Mined and rewritten from the wanim playground; see
plans/Plan-SVG.md §11 for the provenance map.

Heavy, optional native dependencies live behind this package only:
`pango` needs PyGObject + pycairo; `latex` shells out to `latex` + `dvisvgm`.
The lemur parser and AST never import any of it.
"""
