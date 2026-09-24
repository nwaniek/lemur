# Maths

lemur's maths is LaTeX, so formulas copy straight over from papers and notes.
`lmr2svg` typesets every formula with a real TeX installation and bakes the
result into the slide as vector outlines. There is no MathJax, and every
viewer sees the same thing.

## Inline maths

Put it between single dollars, as in LaTeX:

```{lemur-example}
!slide Inline

The Gaussian integral $\int_{-\infty}^{\infty} e^{-x^2}\,dx = \sqrt{\pi}$ sits
on the baseline of the text, and so does $\mathbb{E}[X] = \sum_x x\,p(x)$.
```

Because `$` starts maths, write a literal dollar as `\$` ("it costs \$5"). The
parser warns about `$$` and about lines with an odd number of unescaped `$`,
which catches most forgotten escapes.

## Display maths

A `:: math` block holds a displayed formula. Its indented body is what you would
put between `\[` and `\]`:

```{lemur-example}
!slide Display

:: math
	p(\theta \mid x) = \frac{p(x \mid \theta)\, p(\theta)}{p(x)}
```

Several rows go in one block. Separate them with `\\`, and they are centred.
Mark alignment points with `&`, and they are aligned:

```{lemur-example}
!slide Aligned rows

:: math
	\nabla \cdot \mathbf{E} &= \rho / \varepsilon_0 \\
	\nabla \times \mathbf{B} &= \mu_0 \mathbf{J} + \mu_0 \varepsilon_0 \partial_t \mathbf{E}
```

LaTeX display environments (`align`, `align*`, `gather`, `multline`,
`equation`, `eqnarray`) may be pasted in as they are; lemur maps them to their
in-line equivalents. Equation numbers are not shown. Instead, give the block a
`^ref` and refer to it by name.

```lemur
:: math ^bayes
	p(\theta \mid x) \propto p(x \mid \theta)\, p(\theta)
```

## Unicode input

Formulas may use Unicode symbols directly, and lemur translates them to LaTeX:
Greek letters (`α`, `Σ`), relations and operators (`≤`, `∈`, `→`, `∑`) and
mathematical alphabets (`𝐿`, `ℝ`). That is handy when you paste from other
sources.

## Naming parts of a formula

`\mk{name}{…}` names a part of a formula. It changes nothing by itself, but a
named part can be coloured, labelled and pointed at, step by step:

```{lemur-example}
:step: last

!slide Named parts

:: math
	p(x) = \frac{1}{\mk{z}{Z}} \prod_a \mk{fac}{f_a(x_{\partial a})}

!annotate
	fac: local factors
	z[#c0392b]: the normaliser
```

See [Annotations and arrows](annotations.md) for everything you can do with
named parts.

## Packages and macros

Maths is set with `amsmath`, `amssymb`, `mathtools` and Latin Modern. To add
packages or define macros for a whole deck, give it a LaTeX preamble from a
[`style.py`](../design/style.md):

```python
# style.py
from lemur.style import Style as Base

class Style(Base):
    preamble = "preamble.tex"      # relative to style.py
```

```latex
% preamble.tex (replaces the default preamble, so keep what you need)
\usepackage[T1]{fontenc}
\usepackage{amsmath,amssymb,amsfonts,mathtools}
\usepackage{lmodern}
\usepackage{xcolor}
\usepackage{bm}
\newcommand{\E}{\mathbb{E}}
\newcommand{\KL}[2]{D_{\mathrm{KL}}\!\left(#1 \,\middle\|\, #2\right)}
```

Keep `xcolor` in the preamble: lemur uses it to find named parts.

## When a formula does not fit

A display formula wider than its column is scaled down to fit, and the build
reports a warning so you can decide whether to break it into rows. A formula
with a LaTeX error does not stop the build. Its source is shown in red on the
slide and the error is reported with the slide number.
