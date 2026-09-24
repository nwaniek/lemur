# Writing an emitter

An emitter turns the [AST](../reference/ast.md) into output. Because the AST
is plain JSON, an emitter can be written in any language: run `lmr2ast`, then
read JSON. In Python, the parser can be called directly:

```python
from lemur.parser import Parser, deck_to_ast, load_lines

ast = deck_to_ast(Parser(load_lines("talk.lmr")).parse())
```

## A minimal emitter

This emitter writes a Markdown outline of a talk: slide titles and their
paragraphs.

```python
import json, sys

def inline(nodes):
    out = []
    for n in nodes:
        t = n["type"]
        if t == "text":
            out.append(n["value"])
        elif t in ("strong", "emph", "strike", "underline", "span", "mark"):
            out.append(inline(n.get("content", [])))
        elif t == "code":
            out.append(f"`{n['value']}`")
        elif t == "math":
            out.append(f"${n['tex']}$")
        elif t == "link":
            out.append(f"[{inline(n['content'])}]({n['href']})")
        elif t == "xref":
            out.append(f"[{n['target']}](#{n['target']})")
        elif t == "cite":
            out.append("[" + ", ".join(n["keys"]) + "]")
    return "".join(out)

ast = json.load(sys.stdin)
for block in ast["body"]:
    if block["type"] == "pagebreak":
        print("\n## " + inline(block.get("title", [])))
    elif block["type"] == "para":
        print(inline(block["content"]))
```

```console
$ lmr2ast talk.lmr | python3 outline.py
```

## Things every emitter decides

- **Unknown nodes.** Skip what you don't support, and say so. The AST has a few
  target-specific blocks (`anim`, `shader`, and `embed`, which carries a static
  fallback); an emitter that can't show them should use the fallback or leave
  them out.
- **Reveals.** A `reveal.spec` says on which steps a block or mark is visible.
  A static emitter (a handout, an article) ignores it and shows the final
  state. Note that bounded specs such as `"2"` mean the content disappears
  later.
- **References.** `xref` and `cite` carry symbolic targets. The emitter numbers
  slides, figures and bibliography entries, and resolves the targets.
- **Style hints.** Spans and blocks carry style classes and colours as hints.
  The built-in class names (`bold`, `italic`, `underline`, `strike`, `accent`,
  `center`, `frame`) should be honoured; others are free to map to a theme or
  to be ignored.
- **Presentation.** Everything in `presentation` (theme, transitions, chrome) is
  advice and may be ignored.

## Keeping in step with the language

The schema in `spec/ast.schema.json` is versioned with `astVersion`. Check it,
and refuse versions you don't know. `lemur.ast.check(ast)` does this for Python
emitters.
