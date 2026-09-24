#!/usr/bin/env python3
"""Run the lemur parser (produce the neutral AST) without installing the package.

    python3 lmr2ast.py deck.lmr --ast            # or:  ./lmr2ast.py deck.lmr --ast

A thin wrapper around lemur.parser:main — the same thing as the `lmr2ast` console
script you get after `pip install`, and `python3 -m lemur.parser`. (It cannot be
named `lemur.py`: that would collide with the `lemur/` package on import.)
"""
import os
import sys

# put the repo root on the path so the `lemur` package imports from here
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lemur.parser import main  # noqa: E402

raise SystemExit(main())
