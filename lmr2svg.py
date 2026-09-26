#!/usr/bin/env python3
"""Build a lemur deck into one self-contained HTML file, without installing
the package.

    python3 lmr2svg.py deck.lmr -o deck.html
    python3 lmr2svg.py deck.lmr --watch

Everything is baked to SVG at build time (text via Pango, maths via
LaTeX/dvisvgm): no MathJax, no web fonts, nothing fetched when presenting.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lemur.emit.svg import main  # noqa: E402

raise SystemExit(main())
