"""Global constants: coordinate frame, directions, default palette.

lemur.anim works in a *world* coordinate system that is:

  * 2-dimensional (``(x, y)``; this is a slide tool, SVG is 2D),
  * **y-up** (like maths, unlike SVG -- the flip happens once, in the camera),
  * centred on the origin.

The default frame is 8 units tall and 16/9 * 8 units wide, so ``UP * 4`` is the
top edge and ``RIGHT * 7.111`` the right edge.
"""

from __future__ import annotations

import numpy as np

# --------------------------------------------------------------------------
# frame
# --------------------------------------------------------------------------

FRAME_HEIGHT: float = 8.0
ASPECT_RATIO: float = 16 / 9
FRAME_WIDTH: float = FRAME_HEIGHT * ASPECT_RATIO

#: Pixel size of the rendered viewport at zoom 1.  Only used to convert
#: user-facing pixel quantities (stroke widths, font sizes) into world units.
PIXEL_HEIGHT: int = 1080
PIXEL_WIDTH: int = int(round(PIXEL_HEIGHT * ASPECT_RATIO))

#: How many pixels one world unit spans at the default camera.
PIXELS_PER_UNIT: float = PIXEL_HEIGHT / FRAME_HEIGHT  # 135.0

# --------------------------------------------------------------------------
# directions
# --------------------------------------------------------------------------

ORIGIN = np.array([0.0, 0.0])
UP = np.array([0.0, 1.0])
DOWN = np.array([0.0, -1.0])
RIGHT = np.array([1.0, 0.0])
LEFT = np.array([-1.0, 0.0])

UL = UP + LEFT
UR = UP + RIGHT
DL = DOWN + LEFT
DR = DOWN + RIGHT

X_AXIS = RIGHT
Y_AXIS = UP

TAU = 2 * np.pi
PI = np.pi
DEG = TAU / 360

#: Default gap used by ``next_to`` / ``arrange``.
SMALL_BUFF = 0.1
MED_SMALL_BUFF = 0.25
MED_BUFF = 0.5
LARGE_BUFF = 1.0
DEFAULT_BUFF = MED_SMALL_BUFF

# --------------------------------------------------------------------------
# palette
# --------------------------------------------------------------------------

# A calm, presentation-friendly palette.  Hues are spaced for categorical use
# and hold up in both light and dark themes.
BLUE = "#3b82c4"
TEAL = "#12a594"
GREEN = "#4f9d4f"
YELLOW = "#d9a520"
ORANGE = "#e07a3c"
RED = "#d2504b"
MAROON = "#a5416a"
PURPLE = "#7c5cc4"
PINK = "#d4699a"
GREY = "#888888"
GRAY = GREY
BLACK = "#000000"
WHITE = "#ffffff"

LIGHT_GREY = "#bbbbbb"
DARK_GREY = "#444444"
LIGHT_BLUE = "#7db3e0"
DARK_BLUE = "#24557f"

#: Ordered palette used when something needs "the next distinct colour".
CATEGORICAL = [BLUE, ORANGE, GREEN, RED, PURPLE, TEAL, MAROON, YELLOW]

# --------------------------------------------------------------------------
# defaults
# --------------------------------------------------------------------------

DEFAULT_STROKE_WIDTH: float = 4.0  # in px at zoom 1
DEFAULT_FONT_SIZE: float = 36.0  # in px at zoom 1
DEFAULT_DOT_RADIUS: float = 0.08
DEFAULT_ARROW_TIP_LENGTH: float = 0.25

#: Number of straight segments used when flattening a curve for hit tests etc.
CURVE_SAMPLES: int = 16
