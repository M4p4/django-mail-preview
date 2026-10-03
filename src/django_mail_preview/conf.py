"""Settings for django-mail-preview, each read from Django settings with a default.

Values are looked up on every access, so ``override_settings`` works without any
cache to clear.
"""

from __future__ import annotations

import hashlib
import os
import tempfile
from pathlib import Path
from typing import TypeVar

from django.conf import settings

__all__ = ["default_root", "mail_preview_settings"]

T = TypeVar("T")


def _get(name: str, default: T) -> T:
    value: T = getattr(settings, f"MAIL_PREVIEW_{name}", default)
    return value


def default_root() -> Path:
    """Directory for captured messages when ``MAIL_PREVIEW_ROOT`` isn't set.

    A directory under the system temp dir, named after a hash of ``BASE_DIR`` (or
    of the settings module when there is no ``BASE_DIR``), so projects on one
    machine don't share an inbox.
    """
    project = str(getattr(settings, "BASE_DIR", settings.SETTINGS_MODULE))
    key = hashlib.sha256(project.encode()).hexdigest()[:12]
    return Path(tempfile.gettempdir()) / "django-mail-preview" / key


class MailPreviewSettings:
    @property
    def STORAGE(self) -> str:
        """``"files"``, or the dotted path of a ``BaseStorage`` subclass."""
        return _get("STORAGE", "files")

    @property
    def ROOT(self) -> str | os.PathLike[str]:
        """Directory of the file storage."""
        return _get("ROOT", default_root())

    @property
    def MAX_MESSAGES(self) -> int:
        """Captured messages to keep; the oldest are dropped beyond it."""
        return _get("MAX_MESSAGES", 100)

    @property
    def ALLOW(self) -> str | None:
        """Dotted path of a ``callable(request) -> bool`` that gates the pages.

        ``None`` opens them only while ``DEBUG`` is on.
        """
        return _get("ALLOW", None)

    @property
    def TAGS(self) -> str | None:
        """Dotted path of a ``callable(message) -> Iterable[str]`` that tags a message at capture.

        ``None`` leaves the ``X-Tags`` header as the source.
        """
        return _get("TAGS", None)

    @property
    def PLUS_ADDRESSING(self) -> bool:
        """Whether the part after ``+`` in a recipient's address becomes a tag."""
        return _get("PLUS_ADDRESSING", False)


mail_preview_settings = MailPreviewSettings()
