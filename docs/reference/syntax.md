# Syntax reference

Everything in lemur on one page. The normative specification is `spec/spec.lmr`
in the repository, itself written in lemur.

## Lines

| Line starts with | Meaning |
|---|---|
| `%%` | comment (not inside code bodies); `\%%` for a literal |
| `!name…` | a directive |
| `:: lang`, `:: math` | a code block, a display-maths block |
| `#`, `##`, `###` | a section divider slide; headings within a slide |
| `-`, `*`, `+`, `1.` | list items (static, static, revealed, numbered) |
| `^key: …` | a bibliography entry; `^name: <url>` a named link |
| anything else | text; blank lines separate paragraphs |

Directive shape: **`!name[options]<overlay> text ^ref`**, where the brackets
touch the name. Bodies are indented; the first body line fixes the indentation
prefix, and a dedent ends the block.

## Inline

| Syntax | Meaning |
|---|---|
| `**x**`, `__x__`, `~~x~~`, `++x++` | bold, italic, struck through, underlined |
| `` `x` `` | code |
| `$x$` | inline maths (`\$` for a dollar sign) |
| `\mk{name}{x}` | a named part of a formula |
| `[x]^name` | a named mark in text |
| `[x]{.class #rrggbb bg:#rrggbb}` | a styled span |
| `[x]<spec>` | a run shown on the steps in *spec* |
| `[x]{…}^name<spec>` | the suffixes combine |
| `@ref`, `[x]@ref` | a cross-reference |
| `@key`, `@(k1, k2)`, `[x]@(k1, k2)` | a citation |
| `<https://…>`, `<a@b.c>`, `[x]@(https://…)` | links |
| `\n` | a manual line break |
| `\"`, `\--`, `\*`, `` \` ``, `\@`, `\[`, `\$` | literal characters |
| `--`, `---`, `...`, `"…"`, `'` | smart typography: – — … “…” ’ |

Built-in style classes: `.bold`, `.italic`, `.underline`, `.strike`,
`.accent`, and for blocks `.center` and `.frame`.

## Configuration (before the first slide)

`!title`, `!subtitle`, `!author`, `!institute`, `!date`, `!titleimage path`,
`!logo path`, `!header text`, `!footer text`, `!slidenumbers on|off`,
`!progress top|bottom`, `!madewith`, `!theme name`, `!aspect 16:9|4:3`,
`!transition none|fade|slide|push [none|fade|rise]`. Anywhere: `!include path.lmr`.

## Slides and structure

| Syntax | Meaning |
|---|---|
| `!slide[.classes] Title ^ref` | a slide. Classes: `.center`, `.middle`, `.plain`, `.fill`, `.dark`, or a template name |
| `#[.classes] Title ^ref` | a section divider |
| `##`, `###` | headings within a slide |
| `!notes` + body | speaker notes |

## Steps

| Syntax | Meaning |
|---|---|
| `!pause` | what follows appears on the next step |
| `+ item` | a list item on its own step |
| `<n>`, `<n->`, `<-n>`, `<n-m>`, `<a,b->` | overlay specs: only *n*, from *n*, up to *n*, *n* to *m*, lists |
| `<+->`, `<+>` | relative: from the next step on, only during the next step |
| `+<spec> item`, `-<spec> item` | a list item with an overlay |
| `!when<spec>` + body | a block with an overlay |
| `!stack` + `!layer<spec>` bodies | layers that take each other's place |

## Blocks

| Syntax | Meaning |
|---|---|
| `:: math ^ref` + body | display maths; `\\` rows, `&` alignment |
| `:: lang[1\|3-4] ^ref` + body | code, with per-step line highlights |
| `!table Title ^ref`, `!cols A, B[r], "C, D"[c]`, `!caption …`, `!noheader`, indented rows, `---`/`===` rules | a table |
| `!img Title ^ref`, `!src …` (repeatable), `!caption …`, `!width …`, `!height …`, `!mode overlay\|replace` | an image, optionally layered |
| `!columns[60 40 .classes]` + `!column[.center\|.bottom]` bodies | columns |
| `!style[.classes #color bg:#color]` + body | a styled block |
| `!gap`, `!gap[2em]`, `!gap[fill]` | vertical space |
| `!theorem Title ^ref` + body | environments: `theorem`, `lemma`, `corollary`, `proposition`, `definition`, `proof`, `example`, `remark`, `intuition`, `note`, `warning`, `exercise`, `historical` |
| `!annotate` + `name[#c .bold]: label` lines | colour and label marks, one step per line |
| `!connect` + `a -> b [#c .dashed]` lines | arrows between marks (`->`, `<-`, `<->`, `--`), one step per line |

## Computed figures

| Syntax | Directives |
|---|---|
| `!plot Title ^ref` | `!src script.py`, `!caption`, `!width`, `!height` |
| `!anim Title ^ref` | `!src module.py`, `!viewport body\|full\|x y w h`, `!width`, `!height` |
| `!shader Title ^ref` | `!src shader.glsl`, `!steps N`, `!viewport …`, `!width`, `!height`, `!quality q`, `!sound drone\|aurora` |
| `!compute Title ^ref` | `!src program.wgsl`, `!steps N\|slide`, `!rate R`, `!seed S`, `!warmup T`, `!viewport …`, `!width`, `!height`, `!quality q` |
