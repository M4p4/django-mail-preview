"""Tags of a captured message, fixed when it is captured.

Three sources, merged: the message's ``X-Tags`` header, the function
``MAIL_PREVIEW_TAGS`` names, and, with ``MAIL_PREVIEW_PLUS_ADDRESSING`` on,
the part after ``+`` in each recipient's address.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from email.utils import parseaddr

from django.core.mail import EmailMessage
from django.utils.module_loading import import_string

from django_mail_preview.conf import mail_preview_settings

__all__ = [
    "HEADER",
    "header_tags",
    "hook_tags",
    "normalise",
    "plus_tags",
    "tags_for",
]

HEADER = "X-Tags"
"""The header that carries a message's tags, comma separated; Mailpit reads the same one."""


def tags_for(message: EmailMessage) -> tuple[str, ...]:
    """The tags of a message from every source, normalised."""
    tags = header_tags(message)
    hook = mail_preview_settings.TAGS
    if hook is not None:
        tags += hook_tags(hook, message)
    if mail_preview_settings.PLUS_ADDRESSING:
        tags += plus_tags(message)
    return normalise(tags)


def header_tags(message: EmailMessage) -> list[str]:
    """The comma-separated values of the ``X-Tags`` header, whatever the case of its name."""
    for name, value in message.extra_headers.items():
        if name.lower() == HEADER.lower():
            return str(value).split(",")
    return []


def hook_tags(path: str, message: EmailMessage) -> list[str]:
    """What the function at ``path`` returns for the message.

    An iterable of tags, a comma-separated string like the header, or ``None``
    for none. An error in the function propagates, like any error while
    capturing.
    """
    hook: Callable[[EmailMessage], object] = import_string(path)
    result = hook(message)
    if result is None:
        return []
    if isinstance(result, str):
        return result.split(",")
    if not isinstance(result, Iterable):
        raise TypeError(f"{path} returned {result!r}; expected an iterable of tags.")
    return [str(tag) for tag in result]


def plus_tags(message: EmailMessage) -> list[str]:
    """The part after ``+`` in each recipient's address: ``ada+welcome@example.com`` gives ``welcome``."""
    tags: list[str] = []
    for recipient in message.recipients():
        _, address = parseaddr(recipient)
        local, _, _ = address.rpartition("@")
        _, plus, tag = local.partition("+")
        if plus:
            tags.append(tag)
    return tags


def normalise(tags: Iterable[str]) -> tuple[str, ...]:
    """Lowercased and trimmed, inner whitespace as ``-``, empties dropped, deduplicated, sorted.

    So every tag is one word, and a ``tag:`` term in the search box can name it.
    """
    cleaned = {"-".join(tag.lower().split()) for tag in tags}
    cleaned.discard("")
    return tuple(sorted(cleaned))
