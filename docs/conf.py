"""Sphinx configuration for the lemur documentation.

Build:  make docs            (HTML into build/docs/)
Needs:  pip install -e '.[svg,docs]'  — Sphinx, Furo and MyST, plus everything
        lmr2svg needs (the live examples are built while the docs build).
"""

import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "docs", "_ext"))

project = "lemur"
author = "Nicolai Waniek"
copyright = "2026, Nicolai Waniek"
release = "0.0.3"

extensions = [
    "myst_parser",
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "sphinx.ext.viewcode",
    "sphinx.ext.githubpages",   # writes .nojekyll, so GitHub Pages serves _static/ and _lemur/
    "sphinx_copybutton",
    "lemurdoc",
]

source_suffix = {".md": "markdown", ".rst": "restructuredtext"}
root_doc = "index"
exclude_patterns = ["_build", "snippets", "README.md"]

myst_enable_extensions = ["colon_fence", "deflist", "attrs_inline", "attrs_block"]
myst_heading_anchors = 3

autodoc_member_order = "bysource"
autodoc_typehints = "description"
autodoc_default_options = {"members": True, "undoc-members": False}
# 3-D and text layout pull in Pango; keep autodoc working on machines without it.
autodoc_mock_imports = []

html_theme = "furo"
html_title = "lemur"
html_static_path = ["_static"]
html_css_files = ["lemur.css"]
html_favicon = "_static/logo-light.svg"
# the lemur logo (lemur/assets/logo.svg) in the text colour of each mode
html_theme_options = {
    "light_logo": "logo-light.svg",
    "dark_logo": "logo-dark.svg",
    "source_repository": "",
    "navigation_with_keys": True,
    "light_css_variables": {
        "color-brand-primary": "#2e5e6e",
        "color-brand-content": "#2e5e6e",
    },
    "dark_css_variables": {
        "color-brand-primary": "#6fb3c6",
        "color-brand-content": "#6fb3c6",
    },
}
pygments_style = "friendly"
pygments_dark_style = "monokai"
copybutton_prompt_text = r"\$ "
copybutton_prompt_is_regexp = True
