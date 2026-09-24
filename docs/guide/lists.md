# Lists

## Bullets and numbers

`-` or `*` starts a bullet, `1.` a numbered item. The numbers are recomputed, so
you can write `1.` for every item.

```{lemur-example}
!slide Lists

- a bullet
- another, with **bold** and `code`

1. first
1. second
1. third
```

A list ends at the first blank line. A long item continues on the following
lines if they are indented deeper than its marker:

```lemur
- a long item that goes on
  and on, over two lines
- the next item
```

## Nesting

Indent an item under its parent to nest it. Each level is a list of its own and
may use its own marker.

```{lemur-example}
!slide Nested

- factor graphs
	- variables and factors
	- edges connect them
- message passing
	1. collect
	2. distribute
```

## Revealing items one by one

A `+` item appears on its own step, one keypress each. `-`, `*` and `1.` items
appear with whatever came before them.

```{lemur-example}
!slide One at a time

- shown from the start
+ on the first keypress
+ on the second
	- a nested item appears **with** its parent
+ on the third
```

That last point is general: a counter runs through the items in reading order.
A `+` advances it, and every other item sits at its current value. So a nested
list under a `+` item appears together with that item, which is almost always
what you want.

## Explicit steps

For full control, give an item an [overlay](steps.md#overlay-specs) right after
its marker. The item then shows exactly on those steps, and can disappear
again:

```{lemur-example}
!slide Exactly when

- always there
+<2-> from the second keypress on
-<1> only on the first keypress, then gone
```
