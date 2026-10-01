"""Preview classes, and their discovery from ``previews.py`` in installed apps.

An ``EmailPreview`` subclass only records itself when it's defined. The views
call ``get_previews()``, which imports every app's ``previews`` module and
resolves the recorded classes on each call, so nothing is imported or looked
up until the inbox is opened.
"""

from __future__ import annotations

import importlib
import inspect
from dataclasses import dataclass
from types import FunctionType
from typing import Any, ClassVar

from django.apps import apps
from django.core.exceptions import ImproperlyConfigured
from django.core.mail import EmailMessage
from django.http import HttpRequest, QueryDict
from django.utils.module_loading import autodiscover_modules

__all__ = [
    "RESERVED",
    "EmailPreview",
    "Preview",
    "autodiscover",
    "get_previews",
    "registry",
]

RESERVED = frozenset({"group", "params", "render", "request"})
"""Names a preview method can't have, because ``EmailPreview`` and ``Preview`` use them."""

registry: dict[tuple[str, str], type[EmailPreview]] = {}
"""Every ``EmailPreview`` subclass defined so far, by module and qualified name."""


class EmailPreview:
    """Base class for previews.

    Each public method of a subclass is one preview: it takes no arguments and
    returns an ``EmailMessage`` built from sample data. Inside a method,
    ``self.request`` is the current request (``None`` outside a view) and
    ``self.params`` its query string, so ``?lang=de`` can select a variant.
    """

    group: ClassVar[str | None] = None
    """The sidebar group; the label of the app containing the module unless set."""

    def __init__(self, request: HttpRequest | None = None) -> None:
        self.request = request
        self.params = QueryDict() if request is None else request.GET

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        # Keyed by name, so a re-executed class body (under IPython autoreload,
        # for example) replaces the earlier entry instead of adding a duplicate.
        registry[cls.__module__, cls.__qualname__] = cls


@dataclass(frozen=True)
class Preview:
    """One preview method, as resolved by ``get_previews()``."""

    id: str
    """``<group>.<method>``, shown in the sidebar and used in URLs."""
    group: str
    method: str
    cls: type[EmailPreview]
    description: str
    """The first paragraph of the method's docstring, or an empty string."""

    def render(self, request: HttpRequest | None = None) -> EmailMessage:
        """The message the preview builds.

        Raises ``TypeError`` when the method returns anything else.
        """
        message: object = getattr(self.cls(request), self.method)()
        if not isinstance(message, EmailMessage):
            raise TypeError(
                f"{_name(self.cls)}.{self.method}() must return an EmailMessage, not {type(message).__name__}."
            )
        return message


def autodiscover() -> None:
    """Import ``previews`` from every installed app.

    Safe to call on every request: an imported module is a dictionary lookup,
    an app without the module is skipped, and an error inside one propagates.
    The import caches are invalidated first, so a ``previews.py`` created while
    the server runs is found by the next call.
    """
    importlib.invalidate_caches()
    autodiscover_modules("previews")


def get_previews() -> list[Preview]:
    """Every preview of every ``EmailPreview`` subclass, sorted by id.

    Autodiscovers first, then resolves groups and methods, on each call. Raises
    ``ImproperlyConfigured`` for a method with a reserved name, and for an id
    two classes share.
    """
    autodiscover()
    previews: dict[str, Preview] = {}
    for cls in registry.values():
        group = _group(cls)
        for method, value in vars(cls).items():
            if method.startswith("_") or not inspect.isfunction(value):
                continue
            if method in RESERVED:
                raise ImproperlyConfigured(
                    f"{_name(cls)}.{method}() can't be a preview: {method!r} is reserved. Rename the method."
                )
            preview = Preview(
                f"{group}.{method}", group, method, cls, _description(value)
            )
            if (other := previews.get(preview.id)) is not None:
                raise ImproperlyConfigured(
                    f"Preview id {preview.id!r} is used by both {_name(other.cls)} and {_name(cls)}. Set a different group on one of them."
                )
            previews[preview.id] = preview
    return sorted(previews.values(), key=lambda preview: preview.id)


def _group(cls: type[EmailPreview]) -> str:
    if cls.group is not None:
        return cls.group
    app = apps.get_containing_app_config(cls.__module__)
    return app.label if app is not None else cls.__module__.partition(".")[0]


def _name(cls: type) -> str:
    return f"{cls.__module__}.{cls.__qualname__}"


def _description(function: FunctionType) -> str:
    """The first paragraph of the docstring, on one line."""
    paragraph = inspect.cleandoc(function.__doc__ or "").split("\n\n", 1)[0]
    return " ".join(line.strip() for line in paragraph.splitlines())
