"""A night-sky design for the live-shader deck: near-black ground, cool ink,
an aurora-green accent. (lmr2svg picks up a style.py next to the deck.)"""
from lemur.themes import dark


class Style(dark.Style):
    bg = "#070a12"
    title = "#eef3f8"
    body = "#c9d3de"
    math = "#eef3f8"
    caption = "#8793a3"
    accent = "#6ef3b4"
    rule = "#1f2a38"
    code_bg = "#0d131f"
    serif = ("Source Sans 3", "DejaVu Sans", "sans-serif")
    title_weight = 600
    transition = ("fade", "fade")
