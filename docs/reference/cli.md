# Command-line reference

lemur installs four commands. Each is also a script at the top of the
repository (`python3 lmr2svg.py …`).

## `lmr2svg`

Builds a deck into one self-contained HTML file: text and maths baked to vector
outlines, with a small player for steps, transitions, animations and shaders.

```text
lmr2svg [-h] [-o OUTPUT] [-s STYLE] [-t THEME] [-q {draft,low,medium,high,max}]
        [--wireframe] [--separate-images] [--strict] [-w] [-p PORT] [--no-open]
        input
```

| Option | |
|---|---|
| `input` | the `.lmr` file (the master file of a multi-file talk) |
| `-o, --output FILE` | the output `.html` (default: `<input>.svg.html`, next to the input) |
| `-t, --theme NAME` | a shipped theme (`clean`, `dark`, `journal`) or a theme folder `themes/<NAME>/` next to the deck or on `LEMUR_THEMES`. Overrides everything else |
| `-s, --style FILE` | a `style.py` with the design and templates (default: `style.py` next to the deck, if present) |
| `-q, --quality LEVEL` | outline precision: `draft`, `low`, `medium` (default), `high`, `max` |
| `--separate-images` | write a folder instead of one file (`-o` names the folder; default `<input>_deck/`): `index.html` plus the images in `images/` |
| `--strict` | exit with status 3 if the build reported any warning |
| `--wireframe` | write `<input>.wireframe.html`, showing the design's regions as labelled boxes |
| `-w, --watch` | serve the deck with live reload and rebuild on save |
| `-p, --port PORT` | the port for `--watch` (default 8000) |
| `--no-open` | with `--watch`: don't open a browser |

Exit status: 0 on success; 1 when the input cannot be read or parsed, or when
the theme is unknown; 3 with `--strict` when warnings were reported.

## `lmranim`

Opens one `lemur.anim` module in a live viewer with a timeline, rebuilds it on
save and jumps from a shape to the line that made it. See
[Designing animations](../figures/viewer.md).

```text
lmranim [-h] [-c CLASS] [-t THEME] [-s STYLE] [--aspect {16:9,4:3}]
        [-e EDITOR] [-p PORT] [--no-open]
        module
```

| Option | |
|---|---|
| `module` | the animation module (`.py`), the one a deck's `!anim` `!src` names |
| `-c, --class CLASS` | the `Anim` class to show (default: the last one defined) |
| `-t, --theme NAME` | the stage's theme, as for `lmr2svg` (default: `style.py` next to the module if present, else `clean`) |
| `-s, --style FILE` | a `style.py` for the stage |
| `--aspect RATIO` | the slide format, `16:9` or `4:3` |
| `-e, --editor CMD` | the command that opens a file at a line, with `{file}` and `{line}` filled in (default: `$LEMUR_EDITOR`) |
| `-p, --port PORT` | the port (default 8100) |
| `--no-open` | don't open a browser |

Exit status: 0 when stopped with Ctrl-C; 1 when the module does not exist. A
module that fails to run does not stop the viewer: it shows the traceback until
the next save.

## `lmr2slides`

Builds a deck into an HTML deck **folder** that is rendered by the browser, with
MathJax for maths. See [Emitters](emitters.md) for what it supports.

```text
lmr2slides [-h] [-o DIR] [--theme NAME_OR_DIR] [--theme-dir DIR] [--assets DIR]
           [--print] [--list-themes] [input]
```

| Option | |
|---|---|
| `input` | the `.lmr` file |
| `-o, --output DIR` | the output folder (default: the input's name without extension) |
| `--theme NAME_OR_DIR` | a CSS theme by name or path; overrides the deck's `!theme` |
| `--theme-dir DIR` | add a folder to the theme search path (also `LEMUR_THEMES`, `themes/` next to the deck, and the built-in themes) |
| `--assets DIR` | copy MathJax from `DIR/mathjax/` into the deck, so it works offline (e.g. after `npm install mathjax@4`) |
| `--print` | build the print pages (one per step) on load, for `chrome --headless --print-to-pdf` |
| `--list-themes` | list the themes on the search path and exit |

## `lmr2ast`

Parses a document and prints its AST as JSON (see [The AST](ast.md)). Use it to
inspect how lemur reads a document, or to feed an emitter of your own.

```console
$ lmr2ast talk.lmr > talk.json
```

## Environment variables

| Variable | |
|---|---|
| `LEMUR_THEMES` | extra folders to search for themes (separated by `:`, or `;` on Windows) |
| `LEMUR_EDITOR` | the editor command for `lmranim` (see `--editor`) |
| `LEMUR_CACHE` | where LaTeX results are cached (default `$XDG_CACHE_HOME/lemur`) |
