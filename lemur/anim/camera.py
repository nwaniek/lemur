"""The camera.

The camera is just a rectangle in world space: whatever it covers is what the
viewer sees.  Because it is a mobject, it animates like everything else --
``self.play(self.camera.frame.animate.set_width(4).move_to(dot))``.
"""

from __future__ import annotations

import numpy as np

from . import constants as C
from .mobject import VShape

__all__ = ["Camera", "CameraFrame"]


class CameraFrame(VShape):
    """An invisible rectangle marking the visible region."""

    def __init__(self, width: float = C.FRAME_WIDTH, height: float = C.FRAME_HEIGHT, **kwargs):
        kwargs.setdefault("stroke_width", 0.0)
        super().__init__(**kwargs)
        self._visible = False
        self.name = "CameraFrame"
        self._set_rect(np.zeros(2), width, height)

    def _set_rect(self, center: np.ndarray, w: float, h: float) -> None:
        from . import bezier as bz

        hw, hh = w / 2, h / 2
        corners = np.array([[hw, hh], [-hw, hh], [-hw, -hh], [hw, -hh], [hw, hh]]) + center
        self.set_subpaths([bz.line_handles(corners)], [True])

    # The aspect ratio is fixed by the output resolution, so setting either
    # dimension implies the other.
    def set_width(self, width: float, **kwargs) -> "CameraFrame":  # type: ignore[override]
        return self.set_height(width / C.ASPECT_RATIO)

    def set_height(self, height: float, **kwargs) -> "CameraFrame":  # type: ignore[override]
        self._set_rect(self.get_center(), height * C.ASPECT_RATIO, height)
        return self

    def zoom(self, factor: float) -> "CameraFrame":
        """>1 zooms in."""
        return self.set_height(self.height / factor)

    def focus_on(self, mobject, buff: float = 0.6, min_height: float = 0.8) -> "CameraFrame":
        """Frame a mobject, keeping the output aspect ratio."""
        lo, hi = mobject.get_bbox()
        h = max(float(hi[1] - lo[1]) + 2 * buff, (float(hi[0] - lo[0]) + 2 * buff) / C.ASPECT_RATIO, min_height)
        self.set_height(h)
        return self.move_to((lo + hi) / 2)

    def reset(self) -> "CameraFrame":
        self._set_rect(np.zeros(2), C.FRAME_WIDTH, C.FRAME_HEIGHT)
        return self


class Camera:
    def __init__(self, frame_height: float = C.FRAME_HEIGHT, background=None):
        self.frame = CameraFrame(frame_height * C.ASPECT_RATIO, frame_height)
        self.background = background

    @property
    def center(self) -> np.ndarray:
        return self.frame.get_center()

    @property
    def frame_height(self) -> float:
        return self.frame.height

    @property
    def frame_width(self) -> float:
        return self.frame.width

    def state(self) -> tuple[float, float, float]:
        c = self.center
        return (float(c[0]), float(c[1]), float(self.frame_height))

    def is_default(self) -> bool:
        cx, cy, h = self.state()
        return abs(cx) < 1e-9 and abs(cy) < 1e-9 and abs(h - C.FRAME_HEIGHT) < 1e-9
