"""Output assembly: baked outlines -> SVG -> one self-contained HTML.

`svgdoc` turns placed typeset pieces into an `<svg>` with shared `<defs>` and
`<use>` placements (the static half of the dedup/similarity pass, Plan-SVG
§4.3). The single-file HTML wrapper and the display runtime live alongside it.
"""
