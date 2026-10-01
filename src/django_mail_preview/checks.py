"""System checks for django-mail-preview settings and the capture backend."""

from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from difflib import get_close_matches
from typing import Any

from django.apps import AppConfig
from django.conf import settings
from django.core.checks import CheckMessage, Error, Warning
from django.utils.module_loading import import_string

from django_mail_preview.conf import MailPreviewSettings, mail_preview_settings

__all__ = [
    "BACKEND",
    "backend_is_active",
    "check_allow",
    "check_backend_without_debug",
    "check_max_messages",
    "check_root",
    "check_unknown_settings",
]

BACKEND = "django_mail_preview.backends.EmailBackend"
"""Dotted path of the capture backend."""

PREFIX = "MAIL_PREVIEW_"


def backend_is_active() -> bool:
    """Whether mail goes through the capture backend, by ``MAILERS`` or ``EMAIL_BACKEND``."""
    mailers: Mapping[str, object] | None = getattr(settings, "MAILERS", None)
    if mailers is not None:
        return any(
            isinstance(mailer, Mapping) and mailer.get("BACKEND") == BACKEND
            for mailer in mailers.values()
        )
    # Django 6.1 deprecates EMAIL_BACKEND and warns on each read from outside Django,
    # so it's read only when the project sets it. The default is the SMTP backend.
    if not settings.is_overridden("EMAIL_BACKEND"):
        return False
    backend: str = settings.EMAIL_BACKEND
    return backend == BACKEND


def check_allow(
    app_configs: Sequence[AppConfig] | None, **kwargs: Any
) -> list[CheckMessage]:
    path: object = mail_preview_settings.ALLOW
    if path is None:
        return []
    if not isinstance(path, str):
        problem = f"{path!r} is not a dotted path."
    else:
        try:
            allow = import_string(path)
        except ImportError as error:
            problem = str(error)
        else:
            if callable(allow):
                return []
            problem = f"{path!r} is not callable."
    return [
        Error(
            f"MAIL_PREVIEW_ALLOW can't be used: {problem}",
            hint="Set it to the dotted path of a function that takes the request and returns a bool, or remove it to open the pages only while DEBUG is True.",
            id="django_mail_preview.E001",
        )
    ]


def check_max_messages(
    app_configs: Sequence[AppConfig] | None, **kwargs: Any
) -> list[CheckMessage]:
    value: object = mail_preview_settings.MAX_MESSAGES
    if isinstance(value, int) and not isinstance(value, bool) and value >= 1:
        return []
    return [
        Error(
            f"MAIL_PREVIEW_MAX_MESSAGES must be an integer of 1 or more, not {value!r}.",
            hint="Set it to how many captured messages to keep; the oldest are dropped beyond it.",
            id="django_mail_preview.E003",
        )
    ]


def check_root(
    app_configs: Sequence[AppConfig] | None, **kwargs: Any
) -> list[CheckMessage]:
    root: object = mail_preview_settings.ROOT
    if isinstance(root, (str, os.PathLike)):
        return []
    return [
        Error(
            f"MAIL_PREVIEW_ROOT must be a str or os.PathLike, not {root!r}.",
            hint="Set it to the directory for captured messages, or remove it to use one under the system temp dir.",
            id="django_mail_preview.E004",
        )
    ]


def check_backend_without_debug(
    app_configs: Sequence[AppConfig] | None, **kwargs: Any
) -> list[CheckMessage]:
    if settings.DEBUG or not backend_is_active():
        return []
    return [
        Warning(
            "The django-mail-preview capture backend is active while DEBUG is False, so mail is captured, not delivered.",
            hint="Use the capture backend in development settings only, and a delivering backend elsewhere.",
            id="django_mail_preview.W001",
        )
    ]


def check_unknown_settings(
    app_configs: Sequence[AppConfig] | None, **kwargs: Any
) -> list[CheckMessage]:
    known = [name for name in vars(MailPreviewSettings) if name.isupper()]
    messages: list[CheckMessage] = []
    for name in dir(settings):
        if not name.startswith(PREFIX) or name.removeprefix(PREFIX) in known:
            continue
        matches = get_close_matches(name.removeprefix(PREFIX), known, n=1)
        messages.append(
            Warning(
                f"{name} isn't a django-mail-preview setting.",
                hint=f"Did you mean {PREFIX}{matches[0]}?" if matches else "Remove it.",
                id="django_mail_preview.W002",
            )
        )
    return messages
