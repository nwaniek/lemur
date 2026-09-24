# Text and formatting

## Paragraphs

Consecutive lines form a paragraph. A blank line starts a new one. Line breaks
within a paragraph are just spaces; write `\n` where you want a manual line
break.

```{lemur-example}
!slide Paragraphs

This is one paragraph,
written over two lines.

This is another.\nAnd this starts a new line within it.
```

## Emphasis and code

Four doubled markers, chosen so ordinary prose never triggers them by accident,
plus backticks for code:

| Write | Get |
|---|---|
| `**bold**` | **bold** |
| `__italic__` | *italic* |
| `~~struck~~` | ~~struck~~ |
| `++underlined++` | underlined |
| `` `code` `` | `code` |

They nest, as in `**__bold italic__**`. Since `++` would clash with `C++`, write
that in backticks or escape it as `C\++`.

```{lemur-example}
!slide Emphasis

Some **bold**, __italic__, **__both__**, ~~struck~~ and ++underlined++ text,
and a bit of `inline_code()`.
```

## Smart typography

On every run of prose, straight ASCII becomes real typography:

| Write | Get |
|---|---|
| `--` | – (en dash, for ranges: pages 3--5) |
| `---` | — (em dash) |
| `...` | … |
| `"quotes"`, `don't`, `'90s` | “quotes”, don’t, ’90s |

Code spans, maths and URLs are never touched, so `--flag` in backticks stays
exactly as written.

## Escapes

A backslash makes the next special character literal: `\"` is a straight
quote, `\--` two hyphens, and likewise `\*`, `` \` ``, `\@`, `\[`, `\$`. A
backslash before an ordinary character is just a backslash.

The one escape you will actually need is `\$` for a dollar sign, because `$`
starts [maths](maths.md): "this costs \$5".

## Styled spans

Put text in brackets and attach a `{…}` **style** to it:

```{lemur-example}
!slide Styled spans

A [red word]{#c0392b}, a [highlighted phrase]{bg:#fff3b0},
[bold and blue]{.bold #2c69b0}, and a [themed]{.accent} one.
```

The style uses the same small vocabulary everywhere in lemur:

- `.name` is a named style. Built in are `.bold`, `.italic`, `.underline`,
  `.strike` and `.accent` (the theme's accent colour). Other names are for a
  theme or template to define.
- `#rrggbb` (or a CSS colour name such as `teal`) sets the text colour.
- `bg:#rrggbb` sets a background.

This is deliberately not a formatting language: a span only carries names and
colour hints, and the output decides how they look. For styling whole blocks,
see [styled blocks](layout.md#styled-blocks).

## Links

A bare URL in running text stays plain text. Put it in angle brackets to make
it a link, or give it your own wording with `[text]@(url)`:

```{lemur-example}
!slide Links

See <https://example.org>, write to <someone@example.org>, or read
[the documentation]@(https://example.org/docs).
```

Named links and cross-references to slides, figures and papers are covered in
[References and citations](references.md).

## Headings for emphasis?

Within a slide, `##` and `###` are headings (see
[Slides and structure](structure.md#headings-within-a-slide)). A line that
merely starts with a word in bold is still a paragraph.
