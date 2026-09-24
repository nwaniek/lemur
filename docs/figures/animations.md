# Animations

`!anim` puts an animation on a slide. You write it in Python with `lemur.anim`,
a library in the style of [manim](https://www.manim.community/). It has shapes,
text and maths, animations such as `Create`, `FadeIn` and `Transform`, value
trackers and updaters, and 3‑D views. lemur runs the animation when the deck is
built and stores it as keyframes that the deck's player plays back smoothly.
The deck stays one self-contained file.

```{lemur-example}
:step: 1
:files: anim/hello.py
:source:

!slide A first animation

!anim
	!src hello.py
```

## Beats are steps

`self.next()` marks a **beat**, and each beat is one step of the slide:

- at step 0, the slide shows the animation as it stands at the start (here,
  empty);
- the first keypress plays everything up to the first `self.next()`;
- the second keypress plays up to the second, and so on.

Going back steps back through the beats. On a slide that also reveals other
content, the beats come after it: first everything on the slide is revealed,
step by step, then each further keypress plays the next beat. Several
animations on one slide advance together.

## Directives

| Directive | Meaning |
|---|---|
| `!src file.py` | the animation module (required): it defines a subclass of `Anim` |
| `!viewport body\|full\|x y w h` | where it is drawn. `body` (the default) fills the rest of the slide body below whatever comes before it. `full` covers the whole slide. `x y w h` is a rectangle in design-box pixels |
| `!width`, `!height` | override the width or height of a `body` viewport (a length, e.g. `900px`) |

The animation's drawing area is fitted into the viewport, keeping its aspect
ratio.

If a module defines several `Anim` classes, the last one is used. The module
may import sibling modules from its folder, so shared helpers can live next to
it.

## Writing an animation

An animation subclasses `Anim` and implements `build()`:

```python
from lemur.anim import Anim, Circle, Create, RIGHT

class Hello(Anim):
    def build(self):
        c = Circle()
        self.play(Create(c))                    # animate
        self.next()                             # a beat
        self.play(c.animate.shift(RIGHT * 2))   # animate a method call
        self.wait(0.5)                          # hold
        self.next()
```

The drawing area is 8 units tall and about 14.2 units wide (16:9), with the
origin in the centre. `UP`, `DOWN`, `LEFT` and `RIGHT` are unit vectors.
Colours are hex strings. Shapes default to the deck's text colour.

| In `build()` | |
|---|---|
| `self.play(*animations, run_time=1.0, rate_func="smooth", lag_ratio=0)` | play animations together |
| `self.add(*shapes)`, `self.remove(*shapes)` | show / remove immediately |
| `self.wait(seconds)` | hold the picture |
| `self.next()` | end a beat (one slide step) |
| `self.bring_to_front(*shapes)`, `self.bring_to_back(*shapes)` | change drawing order |

**Shapes**: `Circle`, `Ellipse`, `Arc`, `Dot`, `Line`, `DashedLine`, `Arrow`,
`DoubleArrow`, `CurvedArrow`, `Vector`, `Polygon`, `Polyline`, `Rectangle`,
`Square`, `RoundedRectangle`, `Triangle`, `RegularPolygon`, `Sector`,
`Annulus`, `Angle`, `RightAngle`, `Brace`, `SurroundingRectangle`, `Underline`,
`Cross`, plus groups (`VGroup`).

**Text and maths**: `Text`, `MarkupText`, `MathTex` and `Tex` (typeset with the
same LaTeX as the rest of the deck), `Title`, `BulletList`, `Paragraph`.

**Animations**: `Create`, `Uncreate`, `Write`, `Unwrite`, `DrawBorderThenFill`,
`FadeIn`, `FadeOut`, `GrowFromCenter`, `GrowFromPoint`, `GrowFromEdge`,
`GrowArrow`, `SpinInFromNothing`, `Transform`, `ReplacementTransform`,
`TransformFromCopy`, `FadeTransform`, `MoveAlongPath`, `Rotate`, `Rotating`,
`ScaleBy`, `Shift`, `MoveTo`, `Indicate`, `Circumscribe`, `Flash`, `FocusOn`,
`Wiggle`, `ShowPassingFlash`, `ApplyWave`, and the combinators
`AnimationGroup`, `LaggedStart`, `LaggedStartMap` and `Succession`.

`shape.animate` turns method calls into an animation:
`self.play(c.animate.shift(RIGHT).set_color("#c0392b"))`.

The complete list, with signatures, is in the
[`lemur.anim` reference](../reference/api-anim.rst).

## Things that follow a value

Complex motion is easiest when shapes *follow* a number rather than being
animated one by one. A `ValueTracker` holds a number that can be animated.
Shapes computed from it, whether with an updater or with a `View` helper that
takes a function, follow it automatically:

```{lemur-example}
:step: 1
:files: anim/tracker.py
:source:

!slide A moving tangent

!anim
	!src tracker.py
```

The same idea drives any figure where one parameter moves: a Riemann sum
refining, a Taylor polynomial gaining terms, a particle system evolving.

## Plots in animations

A 2‑D plot is a `View` seen from straight above (`elev=90`). `fit` maps a data
range onto the viewport, and `axes`, `plot`, `area` and `point` draw in data
coordinates:

```python
from lemur.anim import View
v = View(elev=90, viewport=(0, 0, 12.6, 6.2)).fit((-6.3, 6.3), (-1.5, 1.5))
axes = v.axes(x=(-6.3, 6.3, 3.14), y=(-1.5, 1.5, 0.5), z=(0, 0))
curve = v.plot(np.sin, -6.3, 6.3, color="#2b6cb0", stroke_width=5)
```

Views are also how lemur does 3‑D: see [3‑D figures](3d.md).

## File size and speed

The deck stores keyframes, not video. What costs space is shapes whose outline
changes on every frame (a morphing curve, a growing region). Shapes that only
move are cheap, and so are 3‑D shapes: a `View` stores their 3‑D geometry once
and the player projects them. As a guide, a slide with a few animated shapes
adds tens of kilobytes; a particle system with hundreds of moving points adds a
few megabytes.

The examples `animation`, `anim-science` and `anim-calculus` hold more complete
animations: the Lorenz attractor, Taylor series, Fourier synthesis, Riemann sums
and vector fields.
