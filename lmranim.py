#!/usr/bin/env python3
"""Design a lemur.anim animation in a live viewer: timeline, rebuild on save,
jump from a shape to the line of code that made it.

    python3 lmranim.py examples/torus/geodesics.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from lemur.animview import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
