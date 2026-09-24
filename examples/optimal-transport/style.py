"""The illustrated look: warm paper, ink text in a serif that sits well next to
LaTeX's Latin Modern, and a single orange accent (picked up automatically by
lmr2svg because it sits next to the deck)."""
from lemur.style import Style as _Base


class Style(_Base):
    bg = "#fbf9f4"               # paper
    title = "#2b2d42"            # ink
    body = "#33363f"
    math = "#2b2d42"
    caption = "#7a7f8c"
    accent = "#ef7d2d"           # the orange of the figures
    rule = "#e6dfd3"
    code_bg = "#f1ede4"
    serif = ("Source Serif 4", "DejaVu Serif", "serif")
    body_size = 38
    math_size = 38
    title_weight = 600
    title_rule = 2
    transition = ("fade", "fade")
