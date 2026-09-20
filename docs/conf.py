"""Sphinx configuration for pyjev."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pyjev  # noqa: E402

project = "pyjev"
author = "Holger Nahrstaedt"
copyright = "2026, Holger Nahrstaedt"
version = pyjev.__version__
release = pyjev.__version__
root_doc = "index"

extensions = [
    "myst_parser",
    "sphinx.ext.autodoc",
    "sphinx.ext.doctest",
    "sphinx.ext.intersphinx",
    "sphinx.ext.napoleon",
    "sphinx.ext.viewcode",
]
source_suffix = {".md": "markdown"}
myst_enable_extensions = ["colon_fence"]
myst_heading_anchors = 4

napoleon_google_docstring = False
napoleon_numpy_docstring = True
napoleon_include_init_with_doc = True
napoleon_include_private_with_doc = False
napoleon_include_special_with_doc = True
napoleon_use_param = True
napoleon_use_rtype = True

autodoc_default_options = {
    "members": True,
    "show-inheritance": True,
    "member-order": "bysource",
}
autodoc_typehints = "description"
autodoc_preserve_defaults = True

templates_path = ["_templates"]
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store", "README.md"]

html_theme = "sphinx_rtd_theme"
html_theme_options = {"navigation_depth": 4, "titles_only": False}
intersphinx_mapping = {"python": ("https://docs.python.org/3", None)}
