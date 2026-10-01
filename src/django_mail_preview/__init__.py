"""A dev inbox and email previews for Django."""

from __future__ import annotations

from django_mail_preview.registry import EmailPreview, Preview, get_previews

__all__ = ["EmailPreview", "Preview", "get_previews"]
