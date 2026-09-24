#!/usr/bin/env python3
"""Run the (spike) SVG emitter without installing the package.

    python3 lmr2svg.py deck.lmr -o deck.html

Builds a single self-contained HTML slide file — everything baked to SVG at
build time (text via Pango, maths via LaTeX/dvisvgm), no MathJax, no web fonts.
See plans/Plan-SVG.md. This is a spike: one slide, three block types.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lemur.emit.svg import main  # noqa: E402

raise SystemExit(main())
