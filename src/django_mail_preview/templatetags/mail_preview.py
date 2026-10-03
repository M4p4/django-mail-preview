"""Template filters of the inbox pages, loaded with ``{% load mail_preview %}``."""

from __future__ import annotations

from datetime import datetime
from email.utils import parseaddr

from django import template
from django.utils import timezone

__all__ = ["UNITS", "ago", "register", "sender"]

register = template.Library()

UNITS: tuple[tuple[str, int], ...] = (
    ("minute", 60),
    ("hour", 60 * 60),
    ("day", 24 * 60 * 60),
    ("week", 7 * 24 * 60 * 60),
    ("month", 30 * 24 * 60 * 60),
    ("year", 365 * 24 * 60 * 60),
)
"""The steps of ``ago``, each the size of its unit in seconds. ``preview.js`` keeps a copy."""


@register.filter
def ago(then: datetime, now: datetime | None = None) -> str:
    """How long ago ``then`` was, in one unit: "just now", "4 minutes ago", "2 days ago".

    Whole units, rounded down, so the words never run ahead of the clock; a
    time in the future, which a skewed clock can produce, reads "just now".
    The script on the page recomputes the same words while it stays open.
    """
    seconds = int(((now or timezone.now()) - then).total_seconds())
    words = "just now"
    for unit, size in UNITS:
        if seconds < size:
            break
        count = seconds // size
        words = f"{count} {unit}{'' if count == 1 else 's'} ago"
    return words


@register.filter
def sender(value: str) -> str:
    """The display name of an address, or the address itself when it has none.

    ``Scratch <orders@example.com>`` reads "Scratch" in the table, the way Mailpit
    shows it; the whole header stays in the cell's tooltip.
    """
    name, address = parseaddr(value)
    return name or address or value
