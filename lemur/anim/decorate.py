"""decorate — reusable plot furniture: legends and framed panels (insets).

These are plain 2D helpers, usable with any animation (the 3D `View` views, an
`Axes` plot, or hand-placed shapes). Positions are in animation-plane units.
"""

from __future__ import annotations

from typing import Sequence

import numpy as np

from . import bezier as bz
from . import constants as C
from .mobject import VGroup, VShape

__all__ = ["legend", "panel"]


def legend(rows: Sequence, at, font_size: float = 26, gap: float = 0.6,
           swatch: float = 0.55, text_color: str = "#333333") -> VGroup:
    """A legend anchored (top-left) at ``at = (x, y)``. Each row is
    ``(color, label)`` or ``(color, label, kind)`` with ``kind`` in
    ``{"line", "dot"}`` — the sample swatch to draw beside the label."""
    from .shapes import Circle, Line
    from .text import Text

    g = VGroup()
    x, y = float(at[0]), float(at[1])
    for i, row in enumerate(rows):
        color, text = row[0], row[1]
        kind = row[2] if len(row) > 2 else "line"
        yi = y - i * gap
        if kind == "dot":
            sample = Circle(radius=0.11, fill_color=color, fill_opacity=1.0,
                            stroke_width=0).move_to([x + swatch / 2, yi])
        else:
            sample = Line([x, yi], [x + swatch, yi], color=color, stroke_width=3.5)
        label = Text(text, font_size=font_size, color=text_color)
        label.next_to(sample, C.RIGHT, buff=0.22)
        g.add(sample, label)
    return g


def panel(cx: float, cy: float, w: float, h: float, label: str | None = None,
          color: str = "#c9ced3", label_color: str = "#5f6368",
          font_size: float = 24, stroke_width: float = 1.5) -> VGroup:
    """A rectangular frame centred at ``(cx, cy)`` (``w`` × ``h``), with an
    optional caption above it — a border for an inset / sub-view."""
    from .text import Text

    g = VGroup()
    hw, hh = w / 2, h / 2
    rect = VShape(color=color, stroke_width=stroke_width, fill_opacity=0.0)
    corners = np.array([[cx - hw, cy - hh], [cx + hw, cy - hh],
                        [cx + hw, cy + hh], [cx - hw, cy + hh], [cx - hw, cy - hh]])
    rect.set_subpaths([bz.line_handles(corners)], [True])
    g.add(rect)
    if label:
        g.add(Text(label, font_size=font_size, color=label_color).move_to([cx, cy + hh + 0.28]))
    return g
