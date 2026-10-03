"""System checks for django-mail-preview settings and the capture backend."""

from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from difflib import get_close_matches
from typing import Any

from django.apps import AppConfig
from django.conf import settings
from django.core.checks import CheckMessage, Error, Warning
from django.core.exceptions import ImproperlyConfigured
from django.urls import NoReverseMatch, reverse
from django.utils.module_loading import import_string

from django_mail_preview.conf import MailPreviewSettings, mail_preview_settings
from django_mail_preview.storage import storage_class

__all__ = [
    "BACKEND",
    "backend_is_active",
    "callable_problem",
    "check_allow",
    "check_backend_without_debug",
    "check_max_messages",
    "check_plus_addressing",
    "check_root",
    "check_storage",
    "check_tags",
    "check_unknown_settings",
    "check_urls",
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


def callable_problem(path: object) -> str | None:
    """Why ``path`` isn't the dotted path of a callable, or ``None`` when it is."""
    if not isinstance(path, str):
        return f"{path!r} is not a dotted path."
    try:
        target = import_string(path)
    except ImportError as error:
        return str(error)
    if callable(target):
        return None
    return f"{path!r} is not callable."


def check_allow(
    app_configs: Sequence[AppConfig] | None, **kwargs: Any
) -> list[CheckMessage]:
    path: object = mail_preview_settings.ALLOW
    problem = None if path is None else callable_problem(path)
    if problem is None:
        return []
    return [
        Error(
            f"MAIL_PREVIEW_ALLOW can't be used: {problem}",
            hint="Set it to the dotted path of a function that takes the request and returns a bool, or remove it to open the pages only while DEBUG is True.",
            id="django_mail_preview.E001",
        )
    ]


def check_tags(
    app_configs: Sequence[AppConfig] | None, **kwargs: Any
) -> list[CheckMessage]:
    path: object = mail_preview_settings.TAGS
    problem = None if path is None else callable_problem(path)
    if problem is None:
        return []
    return [
        Error(
            f"MAIL_PREVIEW_TAGS can't be used: {problem}",
            hint="Set it to the dotted path of a function that takes the message and returns its tags, or remove it to tag mail from the X-Tags header only.",
            id="django_mail_preview.E005",
        )
    ]


def check_plus_addressing(
    app_configs: Sequence[AppConfig] | None, **kwargs: Any
) -> list[CheckMessage]:
    value: object = mail_preview_settings.PLUS_ADDRESSING
    if isinstance(value, bool):
        return []
    return [
        Error(
            f"MAIL_PREVIEW_PLUS_ADDRESSING must be True or False, not {value!r}.",
            hint="Set it to True to tag a message with the part after + in a recipient's address, or remove it.",
            id="django_mail_preview.E006",
        )
    ]


def check_storage(
    app_configs: Sequence[AppConfig] | None, **kwargs: Any
) -> list[CheckMessage]:
    value: object = mail_preview_settings.STORAGE
    if not isinstance(value, str):
        problem = f"{value!r} is not a dotted path."
    else:
        try:
            storage_class(value)
        except ImproperlyConfigured as error:
            problem = str(error)
        else:
            return []
    return [
        Error(
            f"MAIL_PREVIEW_STORAGE can't be used: {problem}",
            hint='Set it to "files", or to the dotted path of a BaseStorage subclass, or remove it to store messages as files.',
            id="django_mail_preview.E002",
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


def check_urls(
    app_configs: Sequence[AppConfig] | None, **kwargs: Any
) -> list[CheckMessage]:
    # Without a URLconf, as in a script or worker set up with
    # settings.configure(), there are no pages to include.
    if not backend_is_active() or not getattr(settings, "ROOT_URLCONF", None):
        return []
    try:
        reverse("mail_preview:index")
    except NoReverseMatch:
        return [
            Warning(
                "The django-mail-preview capture backend is active, but its pages aren't in the URLconf, so captured mail can't be seen.",
                hint="Add path('__mail-preview__/', include('django_mail_preview.urls')) to the project's urlpatterns.",
                id="django_mail_preview.W003",
            )
        ]
    return []
