# The lemur documentation

The sources of the HTML documentation: Markdown pages (MyST) built with Sphinx
and the Furo theme.

```sh
pip install -e '.[svg,docs]'     # Sphinx, Furo, MyST + what lmr2svg needs
make docs                        # → build/docs/index.html
```

## Live examples

A fenced `lemur-example` block shows a lemur snippet and, below it, the real
output: the snippet is built with `lmr2svg` while the docs build, and embedded
as a live, clickable deck. A snippet that fails to build fails the docs build.

````md
```{lemur-example}
:files: anim/hello.py      (files from docs/snippets/, placed next to the deck)
:source:                   (also show those files)
:step: last                (open fully built; or a step number)
:theme: dark

!slide Hello
!anim
	!src hello.py
```
````

Plain `lemur` code blocks are highlighted by the lexer in `_ext/lemurdoc.py`.
