"""Sphinx configuration for the django-mail-preview documentation."""

from __future__ import annotations

from importlib.metadata import version as package_version

project = "django-mail-preview"
author = "M4p4"
copyright = "2026, M4p4"
release = package_version("django-mail-preview")
version = release

extensions = [
    "myst_parser",
    "sphinx.ext.autodoc",
]

autodoc_member_order = "bysource"

source_suffix = {".md": "markdown"}
exclude_patterns = ["_build"]

myst_heading_anchors = 3

html_theme = "furo"
html_title = "django-mail-preview"
