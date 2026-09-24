"""lemur.anim — write build-time animations for ``!anim`` slides.

A manim-style library: subclass :class:`Anim`, override :meth:`Anim.build`,
and play animations on shapes (:class:`Shape` / :class:`VShape`), text and
maths; 3-D goes through a :class:`View`.

    from lemur.anim import Anim, Circle, Create, RIGHT

    class Hello(Anim):
        def build(self):
            c = Circle()
            self.play(Create(c))     # a beat later, on the next slide step:
            self.next()
            self.play(c.animate.shift(RIGHT * 2))

The emitter runs this at build time (``Anim().render()`` → keyframe IR) and bakes
it into the slide's viewport; the runtime lerps the tracks, with each ``next()``
beat mapped to a slide step.
"""

from .constants import *          # noqa: F401,F403  directions, PI, frame dims, palette
from .color import *              # noqa: F401,F403  colours + helpers
from .mobject import GlyphRef, Group, Shape, ValueTracker, VGroup, VShape  # noqa: F401
from .shapes import *             # noqa: F401,F403  Circle, Line, Dot, Arrow, Rectangle, …
from .animation import *          # noqa: F401,F403  Create, FadeIn, Transform, Write, …
from .scene import Anim, clear_registry, registered_anims  # noqa: F401
from .mobject import set_default_color as _set_shape_color


def set_default_color(color) -> None:
    """Foreground for text/shapes created without an explicit colour. The `!anim`
    emitter calls this with the deck's foreground so a plain ``Text`` or ``Circle``
    reads on the slide."""
    _set_shape_color(color)
    try:
        from .text import set_text_defaults
        set_text_defaults(color=color)
    except Exception:
        pass


from .three import Space3D, View   # noqa: F401  build-time 3D (a view = camera + viewport)
from .decorate import legend, panel  # noqa: F401  legends + framed insets

# Text/MathTex (they lean on lemur.typeset). Plots are unified into `View`
# (a 2D plot is the top-down view, elev=90) — see `three.py`.
try:
    from .text import *           # noqa: F401,F403  Text, MathTex, Tex, …
except Exception:                 # keep the core importable while typeset bridges settle
    pass
