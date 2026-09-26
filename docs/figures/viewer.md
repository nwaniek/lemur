# Designing animations

An animation is a program, and you write it by trying things: move a label,
change a colour, retime a beat, look again. `lmranim` makes that loop short.
It opens one animation module on its own stage, with a timeline under it, and
rebuilds it every time you save.

```console
$ lmranim geodesics.py
lmranim: building geodesics.py …
  built geodesics.py in 4.12s  (31 shapes, 3 beats, 9.0s)

  viewer   http://127.0.0.1:8100/
  watching /home/me/talks/torus  (save to rebuild)
  editor   none — set --editor or $LEMUR_EDITOR to open files from the viewer
```

The module is the same file that a deck's `!anim` `!src` names; nothing in it
changes for the viewer. If it defines several `Anim` classes, the viewer shows
the last one, as a deck would. Pick another with `-c ClassName`.

## The stage and the timeline

The animation fills the stage at the size it has on a slide, with the deck's
theme (or the `style.py` next to the module). Below it, the timeline shows the
whole animation:

- the **beats** (each `self.next()`) as labelled markers: the steps a
  deck's audience sees, one per keypress;
- each `self.play(…)` inside a beat as a small tick;
- the **playhead**, which you drag, or move with the mouse wheel.

The bar above the timeline shows the time, the current beat, and where the
pointer is in animation units, so you can read off a coordinate for
`.shift(…)` or `.move_to(…)` straight from the picture.

## Keys

| Key | |
|---|---|
| space | play / pause |
| ← → | a frame back / on (1/30 s) |
| shift ← → | the previous / next beat |
| Home, End | the start / the end |
| L | loop the current beat |
| `[` `]` | slower / faster (0.1× to 2×) |
| G | a coordinate grid in animation units |
| V | print view: what a PDF shows (for GPU views, the vector still) |
| S | the shapes panel |
| P | what the module printed, and the build's warnings |
| ? | the list of keys |

## From a shape to its line

Point at anything on the stage and the viewer names it: its kind and the line of
your module that created it (`#20 anchor · geodesics.py:19`). The shapes panel
(S) lists every shape grouped by that line; hovering an entry highlights its
shapes on the stage.

Clicking a shape, or a line in the panel, opens that line in your editor. Tell
`lmranim` how to do that with `--editor` or the `LEMUR_EDITOR` environment
variable: a command in which `{file}` and `{line}` are filled in.

```console
$ export LEMUR_EDITOR='vim --servername lemur --remote-silent +{line} {file}'
$ vim --servername lemur geodesics.py      # in one terminal
$ lmranim geodesics.py                     # in another
```

Other editors work the same way, for example `code --goto {file}:{line}`,
`emacsclient -n +{line} {file}` or `subl {file}:{line}`. The viewer only opens
files of the animation: the module, the files next to it, and the modules it
imports.

## Rebuilding

Saving the module rebuilds it, and so does saving anything next to it: a helper
module it imports, a shader, an image, the `style.py`. Imported helpers from
other folders are watched too. The page reloads in place, at the same time on
the timeline, with the same panels open, so you can keep watching the moment
you are working on.

When the module raises an exception, the viewer shows the traceback instead of
the stage. Each of its lines links to the file and line in your editor. Fix it,
save, and the stage comes back.

## Options

```text
lmranim [-h] [-c CLASS] [-t THEME] [-s STYLE] [--aspect {16:9,4:3}]
        [-e EDITOR] [-p PORT] [--no-open]
        module
```

See [the command-line reference](../reference/cli.md#lmranim) for each option.

## Then put it on a slide

The viewer shows the animation exactly as a deck plays it: the same
build, the same player. When it looks right, name it on a slide:

```lemur
!slide Geodesics on a torus

!anim
	!src geodesics.py
```

and build the deck with [`lmr2svg --watch`](../presenting/building.md), which
also rebuilds when the module changes.
