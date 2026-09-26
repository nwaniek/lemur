"""render_html — the neutral AST -> slide-deck DOM (HTML) emitter.

This is the build-time render engine: it turns the neutral document AST
(spec/ast.schema.json) into the slide DOM described by the display contract
(spec/display-contract.md), as an HTML string. It is a pure function of the AST
— no packaging, no I/O, no theme knowledge — and is the Python port of what
runtime.js used to build in the browser (Plan-DisplayModel.md Phase 3). The
runtime is now behavior-only: it drives the DOM this emits (scale, steps, nav,
overview, print, arrows), it never builds it.

`render_deck(doc)` returns a Deck(design_w, design_h, attrs, html): the design
box, the attribute string for the `.deck` element, and its inner HTML (a cover
plus one section per slide).
"""
from __future__ import annotations

import html as _html
import json
from dataclasses import dataclass

# annotation label geometry, in design px (must match runtime.js, which measures
# arrows against it). ANN_TOP_PAD + ANN_ROW_HEIGHT * (#labels) reserves the band.
ANN_TOP_PAD = 21
ANN_ROW_HEIGHT = 60

# void (self-closing) elements we emit
_VOID = {"img", "hr", "br", "meta", "link", "input"}

# a render context resolves the AST's symbolic references against the document
EMPTY_CTX = {"ids": {}, "bib": {}, "labels": {}, "total": 0}


# -- html building ---------------------------------------------------------

def esc(s) -> str:
    """Escape text content (the browser un-escapes it back to the text node)."""
    return _html.escape(str(s), quote=False)


def esc_attr(s) -> str:
    return _html.escape(str(s), quote=True)


def el(tag: str, attrs=None, *kids) -> str:
    """Build an element's HTML. `attrs` is a class string, or a dict of
    attributes — 'class' and 'text' are special, a None/False value is skipped.
    `kids` are already-safe HTML strings (or lists thereof); None/False skipped.
    Mirrors runtime.js `h()`."""
    out = ["<", tag]
    text = None
    if isinstance(attrs, str):
        out.append(f' class="{esc_attr(attrs)}"')
    elif attrs:
        for k, v in attrs.items():
            if v is None or v is False:
                continue
            if k == "text":
                text = v
            elif k == "class":
                out.append(f' class="{esc_attr(v)}"')
            else:
                out.append(f' {k}="{esc_attr(v)}"')
    out.append(">")
    if tag in _VOID:
        return "".join(out)
    if text is not None:
        out.append(esc(text))
    for kid in kids:
        for k in (kid if isinstance(kid, (list, tuple)) else [kid]):
            if k is not None and k is not False:
                out.append(k)
    out.append(f"</{tag}>")
    return "".join(out)


# -- shared helpers (ports of the runtime's) -------------------------------

def inline_text(nodes) -> str:
    """Plain text of an inline run (for slugs, labels, footer fallback)."""
    out = ""
    for n in nodes or []:
        if n.get("type") == "text":
            out += n["value"]
        elif n.get("content"):
            out += inline_text(n["content"])
    return out


def reveal_appear(reveal):
    """The activation step of an open-ended 'n-' spec, else None."""
    if reveal and reveal.get("spec"):
        m = reveal["spec"]
        if m.endswith("-") and m[:-1].isdigit():
            return int(m[:-1])
    return None


def _gate_attrs(reveal) -> dict:
    """A reveal spec -> the data-appear (cumulative 'n-') or data-when attr."""
    if not reveal:
        return {}
    n = reveal_appear(reveal)
    return {"data-appear": str(n)} if n is not None else {"data-when": reveal["spec"]}


def _style_into(attrs: dict, style) -> dict:
    """Fold a neutral style (classes + colour/bg) into an attrs dict that may
    already carry a base class. Mirrors runtime.js applyStyle."""
    if not style:
        return attrs
    classes = [c for c in (attrs.get("class", "").split(" ")) if c]
    classes += style.get("classes", [])
    if classes:
        attrs["class"] = " ".join(classes)
    decl = []
    if style.get("color"):
        decl.append(f"color:{style['color']}")
    if style.get("bg"):
        decl.append(f"background-color:{style['bg']}")
    if decl:
        attrs["style"] = (";".join([attrs["style"]] + decl)
                          if attrs.get("style") else ";".join(decl))
    return attrs


def inject_marks(tex: str, marks) -> str:
    """Re-inject lemur math marks into raw TeX as `\\htmlClass{lmr-a-<name>}{…}`
    at their char spans. Nested spans stay nested (inner closes first, outer
    opens first). Port of runtime.js injectMarks."""
    if not marks:
        return tex
    opens: dict = {}
    closes: dict = {}
    for m in marks:
        opens.setdefault(m["from"], []).append(m)
        closes.setdefault(m["to"], []).append(m)
    out = []
    for i in range(len(tex) + 1):
        for _ in sorted(closes.get(i, []), key=lambda a: -a["from"]):
            out.append("}")
        for m in sorted(opens.get(i, []), key=lambda a: -a["to"]):
            out.append(f"\\htmlClass{{lmr-a-{m['name']}}}{{")
        if i < len(tex):
            out.append(tex[i])
    return "".join(out)


# -- inline nodes -> html --------------------------------------------------

def render_inline(nodes, ctx=EMPTY_CTX) -> str:
    return "".join(inline_node(n, ctx) for n in (nodes or []))


def inline_node(node, ctx) -> str:
    t = node["type"]
    if t == "text":
        return esc(node["value"])
    if t == "break":
        return el("br")
    if t == "strong":
        return el("strong", None, render_inline(node["content"], ctx))
    if t == "emph":
        return el("em", None, render_inline(node["content"], ctx))
    if t == "strike":
        return el("s", None, render_inline(node["content"], ctx))
    if t == "underline":
        return el("u", None, render_inline(node["content"], ctx))
    if t == "code":
        return el("code", {"text": node["value"]})
    if t == "math":
        return esc("\\(" + inject_marks(node["tex"], node.get("marks")) + "\\)")
    if t == "link":
        return el("a", {"href": node["href"]}, render_inline(node["content"], ctx))
    if t == "mark":
        attrs = _style_into({"class": f"lmr-a-{node['name']}"}, node.get("style"))
        attrs.update(_gate_attrs(node.get("reveal")))
        return el("span", attrs, render_inline(node["content"], ctx))
    if t == "span":
        attrs = _style_into({}, node.get("style"))
        attrs.update(_gate_attrs(node.get("reveal")))
        return el("span", attrs, render_inline(node["content"], ctx))
    if t == "xref":
        if ctx["ids"].get(node["target"]):
            inner = (render_inline(node["content"], ctx) if node.get("content")
                     else esc(ctx["labels"].get(node["target"], node["target"])))
            return el("a", {"href": f"#/{node['target']}"}, inner)
        return el("span", {"class": "lmr-badref", "title": "unresolved reference",
                           "text": f"@{node['target']}"})
    if t == "cite":
        parts = []
        if node.get("prefix"):
            parts.append(render_inline(node["prefix"], ctx))
        for key in node["keys"]:
            if ctx["bib"].get(key) is None:
                parts.append(el("span", {"class": "lmr-badref",
                                         "title": "unresolved citation",
                                         "text": f"@{key}"}))
        marks = []
        known = [k for k in node["keys"] if ctx["bib"].get(k) is not None]
        for j, key in enumerate(known):
            if j:
                marks.append(",")
            marks.append(el("a", {"href": f"#/bib-{key}"}, esc(str(ctx["bib"][key]))))
        if marks:
            parts.append(el("sup", "lmr-cite", "[", *marks, "]"))
        return "".join(parts)
    return ""


# -- block nodes -> html ---------------------------------------------------

def render_block(node, ctx=EMPTY_CTX) -> str:
    t = node["type"]
    if t == "para":
        out = el("p", None, render_inline(node["content"], ctx))
    elif t == "heading":
        out = el(f"h{min(node['level'] + 1, 5)}", None,
                 render_inline(node["content"], ctx))
    elif t == "math":
        out = el("div", {"class": "lmr-math",
                         "text": "\\[" + inject_marks(node["tex"], node.get("marks")) + "\\]"})
    elif t == "list":
        out = build_list(node, ctx)
    elif t == "code":
        out = render_code(node)
    elif t == "table":
        out = render_table(node, ctx)
    elif t == "figure":
        out = render_figure(node, ctx)
    elif t == "annotate":
        out = render_annotate(node, ctx)
    elif t == "connect":
        out = render_connect(node)
    elif t == "spacer":
        attrs = {"class": "lmr-gap lmr-gap-fill" if node.get("size") == "fill"
                 else "lmr-gap"}
        if node.get("size") and node["size"] != "fill":
            attrs["style"] = f"height:{node['size']}"
        out = el("div", attrs)
    elif t == "bibliography":
        out = render_bib(node, ctx)
    elif t == "notes":
        out = render_notes(node, ctx)
    elif t == "env":
        out = render_env(node, ctx)
    elif t == "style":
        out = render_style_block(node, ctx)
    elif t == "columns":
        out = render_columns(node, ctx)
    elif t == "stack":
        out = render_stack(node, ctx)
    else:
        out = el("div")
    if node.get("id"):
        out = _with_id(out, node["id"])
    return out


def _with_id(html_str: str, ident: str) -> str:
    """Insert an id attribute right after the opening tag name (a labelled block
    is its own #/<id> anchor). The tag has no id yet (the emitters never set one
    on the outermost element of an id-carrying block)."""
    i = html_str.index(">")
    # skip a self-closing '>' only if needed; our id-carrying blocks aren't void
    return f'{html_str[:i]} id="{esc_attr(ident)}"{html_str[i:]}'


def append_blocks(nodes, ctx) -> str:
    """Render blocks, each wrapped in its reveal gate (notes/annotate never)."""
    out = []
    for node in nodes:
        inner = render_block(node, ctx)
        if node["type"] in ("notes", "annotate") or not node.get("reveal"):
            out.append(inner)
        else:
            n = reveal_appear(node["reveal"])
            gate = ({"class": "lmr-step", "data-appear": str(n)} if n is not None
                    else {"class": "lmr-when", "data-when": node["reveal"]["spec"]})
            out.append(el("div", gate, inner))
    return "".join(out)


def build_list(node, ctx) -> str:
    items = []
    for it in node["items"]:
        li = el("li", _gate_attrs(it.get("reveal")), render_inline(it["content"], ctx))
        items.append(li)
        if it.get("sublist"):
            items.append(build_list(it["sublist"], ctx))
    return el("ol" if node["ordered"] else "ul", None, items)


def render_code(node) -> str:
    attrs = {}
    if node.get("language"):
        attrs["class"] = f"language-{node['language']}"
    if node.get("highlights"):
        m = {}
        for grp in node["highlights"]:
            m[reveal_appear(grp.get("reveal")) or 1] = [str(x) for x in grp["lines"]]
        attrs["data-highlights"] = json.dumps(m, separators=(",", ":"))
    lines = [el("span", {"class": "cl", "data-line": str(i + 1), "text": line})
             for i, line in enumerate(node["source"].split("\n"))]
    return el("pre", "lmr-code", el("code", attrs, lines))


def render_table(node, ctx) -> str:
    def align(i):
        cols = node["columns"]
        a = cols[i]["align"] if i < len(cols) and cols[i].get("align") else "left"
        return f"text-align:{a}"
    body_rows = []
    pending = None
    for row in node["rows"]:
        if row.get("separator"):
            pending = f"lmr-sep-{row['separator']}"
            continue
        cells = [el("td", {"style": align(ci)}, render_inline(cell, ctx))
                 for ci, cell in enumerate(row["cells"])]
        body_rows.append(el("tr", pending, cells))
        pending = None
    tbody = el("tbody", None, body_rows)
    cap = (el("caption", None, render_inline(node["caption"], ctx))
           if node.get("caption") else None)
    thead = (el("thead", None, el("tr", None,
                [el("th", {"style": align(i)}, render_inline(col["heading"], ctx))
                 for i, col in enumerate(node["columns"])]))
             if node.get("header", True) else None)
    title = (el("div", "lmr-tabletitle", render_inline(node["title"], ctx))
             if node.get("title") else None)
    return el("div", "lmr-table", title, el("table", None, cap, thead, tbody))


def render_figure(node, ctx) -> str:
    sized = bool(node.get("width") or node.get("height"))
    decl = []
    if node.get("width"):
        decl.append(f"width:{node['width']}")
    if node.get("height"):
        decl.append(f"height:{node['height']}")
    style = ";".join(decl)

    def img(src, appear=None):
        a = {"src": src, "alt": ""}
        if appear is not None:
            a["data-appear"] = str(appear)
        return el("img", a)

    layers = node.get("layers") or []
    sources = node["sources"]
    if len(sources) == 1:
        media = img(sources[0])
    else:
        imgs = []
        for i, src in enumerate(sources):
            appear = (reveal_appear(layers[i - 1]) or 0) if (i > 0 and i - 1 < len(layers)
                                                             and layers[i - 1]) else None
            imgs.append(img(src, appear))
        media = el("div", "lmr-overlay", imgs)
    cap = (el("div", "lmr-caption", render_inline(node["caption"], ctx))
           if node.get("caption") else None)
    attrs = {"class": f"lmr-figure{' lmr-sized' if sized else ''}"}
    if style:
        attrs["style"] = style
    return el("figure", attrs, media, cap)


def render_annotate(node, ctx) -> str:
    labeled = sum(1 for it in node["items"] if it.get("label"))
    height = ANN_TOP_PAD + ANN_ROW_HEIGHT * labeled if labeled else 0
    callouts = []
    for it in node["items"]:
        a = {"class": "callout",
             "data-appear": str(reveal_appear(it.get("reveal")) or 0),
             "data-anchor": f"lmr-a-{it['mark']}"}
        if it.get("emphasis"):
            a["data-styles"] = " ".join(it["emphasis"])
        if it.get("color"):
            a["style"] = f"--hl:{it['color']};--arrow-color:{it['color']}"
        callouts.append(el("div", a,
                           render_inline(it["label"], ctx) if it.get("label") else None))
    return el("div", {"class": "lmr-annotations", "style": f"min-height:{height}px"},
              callouts)


def render_connect(node) -> str:
    carriers = []
    for lk in node["links"]:
        a = {"class": "lmr-connect",
             "data-from": f"lmr-a-{lk['from']}",
             "data-to": f"lmr-a-{lk['to']}",
             "data-dir": lk["dir"],
             "data-appear": str(reveal_appear(lk.get("reveal")) or 0)}
        if lk.get("styles"):
            a["data-styles"] = " ".join(lk["styles"])
        if lk.get("color"):
            a["style"] = f"--arrow-color:{lk['color']}"
        carriers.append(el("span", a))
    return el("div", "lmr-connects", carriers)


def render_bib(node, ctx) -> str:
    items = []
    for e in node["entries"]:
        a = {"id": f"bib-{e['key']}"}
        if ctx["bib"].get(e["key"]) is not None:
            a["value"] = str(ctx["bib"][e["key"]])
        items.append(el("li", a, render_inline(e["content"], ctx)))
    return el("ol", "lmr-bib", items)


def render_notes(node, ctx) -> str:
    return el("aside", "notes", append_blocks(node["body"], ctx))


def render_env(node, ctx) -> str:
    head = el("div", "lmr-env-head",
              el("span", {"class": "lmr-env-kind", "text": node["kind"]}),
              (el("span", "lmr-env-title", render_inline(node["title"], ctx))
               if node.get("title") else None))
    body = el("div", "lmr-env-body", append_blocks(node["body"], ctx))
    return el("section", f"lmr-env env-{node['kind']}", head, body)


def render_style_block(node, ctx) -> str:
    attrs = _style_into({"class": "lmr-style"}, node.get("style"))
    return el("div", attrs, append_blocks(node["body"], ctx))


def render_columns(node, ctx) -> str:
    cols = []
    for col in node["columns"]:
        weight = col["weight"] if col.get("weight") is not None else 1
        attrs = _style_into({"class": "lmr-column", "style": f"flex:{weight}"},
                            col.get("style"))
        cols.append(el("div", attrs, append_blocks(col["body"], ctx)))
    return el("div", _style_into({"class": "lmr-columns"}, node.get("style")), cols)


def render_stack(node, ctx) -> str:
    layers = []
    for lyr in node["layers"]:
        layers.append(el("div", {"class": "lmr-layer", "data-when": lyr["reveal"]["spec"]},
                         append_blocks(lyr["body"], ctx)))
    return el("div", "lmr-stack", layers)


# -- slide / cover / deck --------------------------------------------------

def slugify(text: str) -> str:
    import re
    s = re.sub(r"[^a-z0-9-]+", "-", (text or "").lower())
    s = re.sub(r"^-+|-+$", "", s)
    return s or "slide"


def design_box(aspect):
    return (1440, 1080) if aspect == "4:3" else (1920, 1080)


def build_chrome(pres, meta) -> dict:
    return {
        "header": pres.get("header") or [],
        "footer": pres.get("footer")
        or ([{"type": "text", "value": meta["title"]}] if meta.get("title") else []),
        "logo": pres.get("logo") or "",
        "slideNumbers": pres.get("slideNumbers") is not False,
    }


def paginate(body):
    pages = []
    cur = None
    for node in body:
        if node["type"] == "pagebreak":
            cur = {"pb": node, "blocks": []}
            pages.append(cur)
        elif cur is not None:
            cur["blocks"].append(node)
    return pages


def collect_symbols(body) -> dict:
    ctx = {"ids": {}, "bib": {}, "labels": {}, "total": 0}
    bibn = [0]

    def visit(nodes):
        for node in nodes:
            if not isinstance(node, dict):
                continue
            if node.get("id"):
                ctx["ids"][node["id"]] = True
                ctx["labels"].setdefault(
                    node["id"],
                    inline_text(node.get("title") or node.get("content")
                                or node.get("caption")) or node["id"])
            if node["type"] == "bibliography":
                for e in node["entries"]:
                    bibn[0] += 1
                    ctx["bib"][e["key"]] = bibn[0]
            elif node["type"] == "columns":
                for c in node["columns"]:
                    visit(c["body"])
            elif node["type"] == "stack":
                for lyr in node["layers"]:
                    visit(lyr["body"])
    visit(body)
    return ctx


def madewith_el() -> str:
    """`!madewith`: the logo (inline SVG in ``currentColor``, so it takes the
    wordmark's colour) and "made with **lemur**", for the bottom-left corner of
    the first slide."""
    import os
    logo = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "logo.svg")
    mark = None
    if os.path.exists(logo):
        with open(logo, encoding="utf-8") as fh:
            mark = fh.read().strip().replace("<svg ", '<svg aria-hidden="true" ', 1)
    return el("div", "lmr-madewith", mark, el("span", None, "made with ", el("b", {"text": "lemur"})))


def render_cover(meta, pres, badge=None) -> str:
    byline = [x for x in ([*meta.get("authors", []), meta.get("affiliation"),
                           meta.get("date")]) if x]
    content = el("div", "stage-content",
                 (el("div", "lmr-title-image", el("img", {"src": pres["titleImage"], "alt": ""}))
                  if pres.get("titleImage") else None),
                 el("h1", {"text": meta.get("title", "")}),
                 (el("p", {"class": "lmr-title-subtitle", "text": meta["subtitle"]})
                  if meta.get("subtitle") else None),
                 el("hr", "lmr-title-rule"),
                 (el("p", {"class": "lmr-byline", "text": " · ".join(byline)})
                  if byline else None))
    return el("section", {"class": "slide cover", "aria-roledescription": "slide"},
              el("div", "stage", el("div", "layer-bg"), content, badge))


def render_slide(page, number, ctx, chrome, badge=None) -> str:
    pb = page["pb"]
    kind = pb.get("role") or "content"
    variant = (" " + " ".join(pb["variant"])) if pb.get("variant") else ""
    has_fill = any(b["type"] == "spacer" and b.get("size") == "fill"
                   for b in page["blocks"])
    show_chrome = kind != "section"

    body = el("div", "lmr-body", append_blocks(page["blocks"], ctx))
    title = (el("h1" if kind == "section" else "h2", None, render_inline(pb["title"], ctx))
             if pb.get("title") else None)
    content = el("div", "stage-content", title, body)

    has_footer = bool(chrome["footer"])
    show_number = chrome["slideNumbers"] and number is not None
    footer = None
    if has_footer or show_number:
        footer = el("div", "lmr-footer",
                    (el("span", "lmr-footer-text", render_inline(chrome["footer"], ctx))
                     if has_footer else el("span")),
                    (el("span", {"class": "lmr-pageno",
                                 "text": f"{number} / {ctx['total']}"})
                     if show_number else None))

    # named layers, stacked in the stage (Plan-DisplayModel §3.2): the background
    # and the chrome (header/logo/footer) are each one swappable subtree; the
    # content layer is .stage-content, the overlay layer is the runtime's arrows.
    header_el = (el("div", "lmr-header", render_inline(chrome["header"], ctx))
                 if show_chrome and chrome["header"] else None)
    logo_el = (el("img", {"class": "lmr-logo", "src": chrome["logo"], "alt": ""})
               if show_chrome and chrome["logo"] else None)
    chrome_layer = (el("div", "layer-chrome", header_el, logo_el, footer)
                    if (header_el or logo_el or footer) else None)
    stage = el("div", "stage", el("div", "layer-bg"), content, chrome_layer, badge)

    ident = pb.get("id") or f"{slugify(inline_text(pb.get('title')))}-{number}"
    cls = f"slide {kind}{variant}{' has-fill' if has_fill else ''}"
    return el("section", {"class": cls, "id": ident, "aria-roledescription": "slide"},
              stage)


@dataclass
class Deck:
    design_w: int
    design_h: int
    attrs: str          # attribute string for the <div class="deck" …>
    html: str           # inner HTML: a cover + one <section> per slide


def render_deck(doc) -> Deck:
    """Build the whole deck DOM (as HTML) from the neutral document AST."""
    meta = doc.get("meta") or {}
    pres = doc.get("presentation") or {}
    w, h = design_box(pres.get("aspect"))
    tr = pres.get("transition") or {}
    parts = [
        f'data-design-w="{w}"', f'data-design-h="{h}"',
        f'data-transition="{esc_attr(tr.get("across") or "none")}"',
        f'data-step-transition="{esc_attr(tr.get("step") or "fade")}"',
    ]
    if pres.get("progress"):
        parts.append(f'data-progress="{esc_attr(pres["progress"].get("position") or "bottom")}"')
    parts.append(f'style="--design-w:{w}px;--design-h:{h}px"')
    attrs = " ".join(parts)

    body = doc.get("body") or []
    ctx = collect_symbols(body)
    chrome = build_chrome(pres, meta)
    pages = paginate(body)
    ctx["total"] = len(pages)
    out = []
    badge = madewith_el() if pres.get("madeWith") else None
    if meta.get("title"):
        out.append(render_cover(meta, pres, badge))
        badge = None
    for i, page in enumerate(pages):
        out.append(render_slide(page, i + 1, ctx, chrome, badge if i == 0 else None))
    return Deck(w, h, attrs, "".join(out))
