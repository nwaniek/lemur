#!/usr/bin/env python3
"""Run the lemur HTML slide-deck emitter without installing the package.

    python3 lmr2slides.py deck.lmr -o out/       # or:  ./lmr2slides.py deck.lmr -o out/

A thin wrapper around lemur.emit.slides:main — the same thing as the `lmr2slides`
console script you get after `pip install`, and `python3 -m lemur.emit.slides`.
"""
import os
import sys

# put the repo root on the path so the `lemur` package imports from here
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lemur.emit.slides import main  # noqa: E402

raise SystemExit(main())
