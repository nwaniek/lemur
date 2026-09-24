# Installation

lemur is a Python package (Python ≥ 3.10). The parser itself has no
dependencies. Building slides with `lmr2svg` needs a text shaper, a TeX
installation and a few Python packages.

## Requirements

| What | Why |
|---|---|
| `numpy` | geometry of outlines and animations |
| `pycairo`, `PyGObject` (Pango) | text shaping: every glyph becomes an outline |
| a TeX distribution with `latex` and `dvisvgm` | maths (TeX Live and MiKTeX both work) |
| `pygments` | syntax highlighting of code blocks |
| `matplotlib` *(optional)* | `!plot` figures |
| a browser with WebGL 2 *(when presenting)* | `!shader` slides |

On most Linux distributions, Pango and PyGObject come from the system
packages. For example:

```console
$ sudo apt install python3-gi gir1.2-pango-1.0 python3-cairo texlive-latex-extra dvisvgm   # Debian/Ubuntu
$ sudo pacman -S python-gobject python-cairo pango texlive-latexextra                      # Arch
$ brew install pygobject3 pango && brew install --cask mactex                               # macOS
```

## Installing lemur

From a checkout of the repository:

```console
$ pip install -e '.[svg]'           # lmr2svg and its Python dependencies
$ pip install -e '.[svg,plot]'      # … plus matplotlib for !plot
```

This installs three commands: `lmr2svg`, `lmr2slides` and `lmr2ast`. You can
also run them straight from the checkout without installing:

```console
$ python3 lmr2svg.py talk.lmr -o talk.html
```

If PyGObject comes from your system packages, create any virtual environment
with `--system-site-packages` so it can see them.

## Check the installation

```console
$ printf '!slide Hello\n\nIt **works**: $e^{i\\pi} + 1 = 0$\n' > hello.lmr
$ lmr2svg hello.lmr -o hello.html
wrote hello.html  (… placements, … distinct outlines)
```

Open `hello.html` in a browser. If Pango or LaTeX is missing, lmr2svg says so.
Maths that fails to typeset is shown in red on the slide and reported as a
warning, and the rest of the deck still builds.

## The typesetting cache

LaTeX runs are cached on disk, so rebuilding a deck only typesets maths that
changed. The cache lives in `$XDG_CACHE_HOME/lemur` (usually `~/.cache/lemur`).
Set `LEMUR_CACHE` to put it elsewhere. Deleting it is always safe.
