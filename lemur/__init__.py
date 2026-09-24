"""lemur — a light markup language and slide compiler.

The package is a stable **core** plus an extensible family of **emitters**:

  - ``lemur.parser``      the parser: a ``.lmr`` document -> the neutral AST
                          (also the ``lmr2ast`` command / ``lmr2ast.py``)
  - ``lemur.ast``         the shared AST contract — version, node vocabulary,
                          load/validate
  - ``lemur.emit``        the emitters that consume the AST (the growth surface):
      - ``lemur.emit.slides``  AST -> a self-contained HTML deck
                               (also the ``lmr2slides`` command / ``lmr2slides.py``)
      - ``lemur.emit.html``    the build-time HTML node rendering it uses
      - (``lemur.emit.tex``    AST -> LaTeX, planned — ``lmr2tex``)
  - ``lemur/assets/``     the slide renderer shipped with the package:
                          ``runtime.js``, the CSS, the built-in themes, the fonts.

Command line, from the repo (no install): ``python3 lmr2ast.py doc.lmr --ast``
and ``python3 lmr2slides.py doc.lmr -o out/`` (or ``./lmr2slides.py …``). After
``pip install`` the equivalents are the ``lmr2ast`` / ``lmr2slides`` console
scripts, or ``python3 -m lemur.parser`` / ``python3 -m lemur.emit.slides``.

The parser's public names are re-exported here, so ``from lemur import Parser``
(and the rest of the parser API) works unchanged.
"""
import importlib

__version__ = "0.0.3"

# Submodules and the re-exported parser API resolve lazily, on first attribute
# access (PEP 562): being lazy keeps ``python3 -m lemur.parser`` from warning
# that the module was imported by this package before it runs as ``__main__``.
_SUBMODULES = frozenset({"ast", "parser", "emit"})


def __getattr__(name):
    if name in _SUBMODULES:
        return importlib.import_module(f"{__name__}.{name}")
    parser = importlib.import_module(f"{__name__}.parser")
    try:
        return getattr(parser, name)
    except AttributeError:
        raise AttributeError(
            f"module {__name__!r} has no attribute {name!r}") from None


def __dir__():
    parser = importlib.import_module(f"{__name__}.parser")
    return sorted(set(globals()) | _SUBMODULES | set(vars(parser)))
