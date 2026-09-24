"""Shipped SVG themes, each a :class:`lemur.master.Style` subclass. Subclass one
in your ``style.py`` and override a few fields::

    from lemur.themes import journal
    from lemur.style import Style, Region

    class Style(journal.Style):
        accent = "#c8a24a"
"""
from . import clean, dark, journal  # noqa: F401

__all__ = ["clean", "dark", "journal"]
