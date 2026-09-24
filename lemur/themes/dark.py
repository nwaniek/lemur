"""The ``dark`` theme — light text on a near-black ground."""
from lemur.master import Region, Style as _Base  # noqa: F401


class Style(_Base):
    bg = "#0d1117"
    title = "#e6edf3"
    body = "#c2ccd6"
    math = "#e6edf3"
    code = "#c9d4e0"
    code_bg = "#161b22"
    caption = "#8b98a5"
    rule = "#30363d"
    accent = "#6cb6ff"
    code_keyword = "#ff7b72"
    code_string = "#7ee787"
    code_number = "#d2a8ff"
    code_comment = "#8b949e"
    code_function = "#6cb6ff"
    code_type = "#79c0ff"
    code_highlight = "#f2cc60"
