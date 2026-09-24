"""The document layout engine: AST blocks -> positioned outline pieces.

This is the part that has no counterpart in wanim (which positions everything by
hand): it replaces what CSS did in the browser-rendered path. A "piece" is
``(subpaths, closed, fill_hex)`` in em units (y-up, first-baseline at y=0), which
the emitter transforms into the design box and hands to the dedup layer.

Built constrained-first (Plan-SVG §4.4): one region, vertical flow. `inline`
handles runs (mixed text, styling and inline maths, with wrapping); block layout
lives in the emitter until it grows enough to move here.
"""
