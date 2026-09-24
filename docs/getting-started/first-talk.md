# Your first talk

This tutorial writes a short talk from an empty file. It takes about fifteen
minutes and touches the ideas you will use every day: slides, steps, maths,
annotations, a theme and a figure. Each section adds to the same file,
`talk.lmr`.

## 1. A title and two slides

Create `talk.lmr`:

```{lemur-example}
!title    Gradient Descent
!subtitle Walking downhill, one step at a time
!author   Ada Lovelace
!date     Spring 2026

!slide The idea

To minimise a function, repeatedly take a small step against its gradient.

!slide Why it works

Near a point, a smooth function looks like a plane, and the gradient is the
direction in which that plane rises fastest.
```

Build it and open the result:

```console
$ lmr2svg talk.lmr -o talk.html
```

The lines before the first slide are **configuration**. `!title`, `!subtitle`,
`!author` and `!date` make the title slide (the *cover*), and the title also
appears in every slide's footer. `!slide Title` starts a slide. Everything up to
the next `!slide` belongs to it, and blank lines separate paragraphs.

:::{tip}
While writing, let lemur rebuild on every save and reload the browser for you:

```console
$ lmr2svg talk.lmr --watch
```
:::

## 2. Build it up step by step

A talk rarely shows a whole slide at once. Mark list items with `+` instead of
`-` to reveal them one keypress at a time, and use `!pause` to hold back
everything that follows:

```{lemur-example}
!slide The idea

To minimise a function, repeatedly take a small step against its gradient:

+ start somewhere
+ look at the slope
+ step downhill, and repeat

!pause

This is **gradient descent**.
```

Click the preview to step through it. Each slide has one step counter. Step 0 is
the slide as it first appears, and every keypress advances it. See
[Steps and overlays](../guide/steps.md) for the full story.

## 3. Maths

Inline maths is LaTeX between single dollars. Display maths is a `:: math` block
with the LaTeX indented below it:

```{lemur-example}
!slide The update rule

With step size $\eta > 0$, each iteration moves $x$ against the gradient:

:: math
	x_{t+1} = x_t - \eta\, \nabla f(x_t)
```

Indentation is how lemur knows where a block ends. The first indented line
sets the indentation, and the block ends at the first line that is indented
less.

## 4. Explain the equation

Name parts of an equation with `\mk{name}{…}`. An `!annotate` block then colours
each named part and points at it with a label, one keypress per line:

```{lemur-example}
:step: last

!slide The update rule

:: math
	x_{t+1} = x_t - \mk{eta}{\eta}\, \mk{grad}{\nabla f(x_t)}

!annotate
	grad: the direction of steepest ascent
	eta[#c0392b]: how far to step
```

lemur computes the label and arrow positions from the typeset equation. If you
change the equation, the arrows follow.

## 5. A picture

Images come in an `!img` block. Its `!src` is a path relative to the `.lmr`
file:

```lemur
!slide A valley

!img
	!src figs/valley.png
	!caption Level sets of $f$ and the path of the iterates.
	!width 70%
```

If a figure is better computed than drawn, `!plot` runs a matplotlib script
instead (see [Plots](../figures/plots.md)).

## 6. Two columns

```{lemur-example}
!slide Too small, too large

!columns[50 50]
	!column
		**Small $\eta$**: safe, but slow.

		+ many tiny steps
	!column
		**Large $\eta$**: fast, until it overshoots.

		+ oscillates, or diverges
```

`!columns[50 50]` splits the slide. Each `!column` holds ordinary lemur,
indented beneath it.

## 7. Give it a look

Add a theme to the configuration:

```{lemur-example}
:theme: dark

!slide The update rule

:: math
	x_{t+1} = x_t - \eta\, \nabla f(x_t)
```

`!theme dark` (or `--theme dark` on the command line) picks one of the shipped
themes: `clean`, `dark` and `journal`. To go further, a `style.py` next to the
deck can change colours, fonts, the layout and even how individual slides are
drawn. See [Themes](../design/themes.md) and [`style.py`](../design/style.md).

## 8. Present it

Open `talk.html` in any browser, press F11 for full screen, and use → / ← (or a
presenter remote) to step. Press `o` for an overview of all slides. The address
bar tracks `#/<slide>/<step>`, so a reload brings you back to the same place.

## Where next

- The [guide](../guide/index.md) covers every construct, with live examples.
- A longer talk is best split into files: see
  [multi-file talks](../guide/structure.md#multi-file-talks).
- For animations, 3‑D figures and live shaders, see *Figures that compute*
  in the navigation.
