"""The ``journal`` theme — a warm serif, academic look."""
from lemur.master import Region, Style as _Base


class Style(_Base):
    bg = "#fbfaf7"
    title = "#2b2b2b"
    body = "#2b2b2b"
    math = "#2b2b2b"
    code = "#2b2b2b"
    code_bg = "#efeae0"
    caption = "#6b6459"
    rule = "#d9d2c4"
    accent = "#8a4b2f"
    code_keyword = "#8a4b2f"
    code_string = "#3a7d44"
    code_number = "#7a4b94"
    code_comment = "#9a938a"
    code_function = "#2e5e6e"
    code_type = "#2e6e5e"
    code_highlight = "#e8c56a"
    serif = ("Source Serif 4", "Noto Serif", "DejaVu Serif", "serif")
    title_size = 56
    title_weight = 700
    title_rule = 2
    title_region = Region(120, 76, 1680, None)
    body_region = Region(120, 216, 1680, 790)
