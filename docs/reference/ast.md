# The AST

Every lemur tool starts by parsing the document into a neutral **document
tree**, the AST. It is the interface between the parser and the emitters, and
the natural starting point for a tool of your own: a linter, a converter, a word
count, a new output format.

```console
$ lmr2ast talk.lmr > talk.json
```

The AST describes an *authored document*, not rendered output. It has no
pixels, no CSS classes and no resolved reference numbers. Presentation is kept
as intent (reveal specs, roles, style hints), and each emitter interprets that
intent in its own way. The exact shape is given by a JSON Schema,
`spec/ast.schema.json` in the repository.

## Shape

```text
{
  "astVersion": 1,
  "meta":         { "title": "…", "subtitle": "…", "authors": ["…"], "affiliation": "…", "date": "…" },
  "presentation": { "theme": "…", "transition": { … }, "header": "…", "footer": "…", … },
  "body": [ …blocks… ]
}
```

- **`meta`** is what the document *is*: title, authors, date. An emitter
  decides whether to make a title page from it.
- **`presentation`** holds hints that an emitter *may* honour: theme, aspect,
  transition, chrome.
- **`body`** is a flat list of blocks. A `pagebreak` block starts each slide or
  section and carries its title, `id` and classes.

## Blocks

| `type` | from |
|---|---|
| `pagebreak` | `!slide`, `#` |
| `heading` | `##`, `###` |
| `para` | a paragraph |
| `list` (of `listItem`) | list items |
| `math` | `:: math` |
| `code` | `:: lang` |
| `table` | `!table` |
| `figure` | `!img` |
| `plot`, `anim`, `shader` | `!plot`, `!anim`, `!shader` |
| `columns`, `stack` | `!columns`, `!stack` |
| `env` | environments (`kind`: `theorem`, `proof`, …) |
| `style` | `!style` |
| `spacer` | `!gap` |
| `annotate`, `connect` | `!annotate`, `!connect` |
| `notes` | `!notes` |
| `bibliography` | `^key:` entries |

Blocks that can be referred to carry an `id` (from `^ref`). Blocks that appear
on a step carry a `reveal`, whose `spec` is an overlay spec such as `"2-"` or
`"1,3-"`. The source forms `+`, `!pause` and `<+->` all turn into explicit specs
in the AST.

## Inline nodes

`text`, `strong`, `emph`, `strike`, `underline`, `code`, `math`, `link`,
`xref` (a `@ref`), `cite`, `mark` (a named span, optionally with a `reveal`),
`span` (a styled span) and `break`.

## Example

```lemur
!slide Results ^results

By the argument in @defs, sum-product is exact on trees @pearl1988.
```

becomes (abridged):

```json
[
  { "type": "pagebreak", "id": "results",
    "title": [ { "type": "text", "value": "Results" } ] },
  { "type": "para", "content": [
      { "type": "text", "value": "By the argument in " },
      { "type": "xref", "target": "defs" },
      { "type": "text", "value": ", sum-product is exact on trees " },
      { "type": "cite", "keys": ["pearl1988"] },
      { "type": "text", "value": "." } ] }
]
```

## Versioning

`astVersion` is the version of the AST contract. An emitter checks it and
refuses a version it doesn't know, rather than mis-rendering it. The Python
package offers `lemur.ast.load(path)` and `lemur.ast.loads(text)`, which
validate the top-level shape and version.
