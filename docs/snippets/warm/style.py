from lemur.style import Style, Region
from lemur.themes import journal


class Style(journal.Style):          # start from `journal`, change a few fields
    accent = "#c0661f"
    title = "#5b2a0e"
    title_size = 60
    body_region = Region(96, 170, 1728, 838)
    transition = ("push", "rise")
