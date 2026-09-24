# Environments

For scientific and technical talks, lemur knows a fixed set of **semantic
environments**: titled boxes for theorems, proofs, definitions and friends. Each
takes an optional title and `^ref`, and an indented body that may hold anything:
text, maths, lists, code, even other environments.

```{lemur-example}
!slide Theorem and proof

!theorem Fixed point on a tree ^bp-fix
	On a tree, sum-product converges to the exact marginals in a finite
	number of steps.

!proof
	A leaf-to-root then root-to-leaf sweep stabilises every message.
```

A proof ends with an end-of-proof mark (∎) by itself.

The kinds are:

| | | |
|---|---|---|
| `!theorem` | `!lemma` | `!corollary` |
| `!proposition` | `!definition` | `!proof` |
| `!example` | `!remark` | `!intuition` |
| `!note` | `!warning` | `!exercise` |
| `!historical` | | |

Environments **nest**. A dedent ends the innermost one:

```{lemur-example}
!slide Nesting

!definition Convexity
	A set is convex if it contains every segment between its points.

	!remark
		Intersections of convex sets are convex.

!warning
	A dedent ends the innermost environment.
```

The theme draws each kind; a `style.py` can restyle them. Numbering ("Theorem
2.3") is left to the output. To refer to an environment, give it a `^ref` and
write `@ref`.

The set is fixed on purpose. lemur has no macro system, so you cannot define
new environment kinds. For a one-off box, use a [styled block](layout.md#styled-blocks).
