"""The capture backend: every message sent through it is stored for the inbox."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime, timezone
from email.generator import BytesGenerator
from email.message import Message
from io import BytesIO
from typing import Any

from django.core.mail import EmailMessage
from django.core.mail.backends.base import BaseEmailBackend

from django_mail_preview.storage import MessageMeta, get_storage, new_id

__all__ = ["EmailBackend"]


class EmailBackend(BaseEmailBackend):
    """Store messages for the inbox instead of delivering them.

    All configuration is in the ``MAIL_PREVIEW_*`` settings, so the backend
    takes no ``OPTIONS``. ``fail_silently`` is accepted and ignored: a capture
    failure, such as an unwritable directory, always raises, because silently
    losing mail in development is worse than a traceback.
    """

    def __init__(self, fail_silently: bool = False, **kwargs: Any) -> None:
        # fail_silently stays here: Django 6.1 deprecates it on the base class.
        super().__init__(**kwargs)

    def send_messages(self, email_messages: Iterable[EmailMessage]) -> int:
        storage = get_storage()
        count = 0
        for message in email_messages:
            # Called once: it validates the headers, and every call mints a new
            # Message-ID.
            mime = message.message()
            raw = _serialise(mime)
            captured = datetime.now(timezone.utc)
            meta = MessageMeta(
                id=new_id(captured),
                subject=str(message.subject),
                from_email=message.from_email,
                to=tuple(message.to),
                cc=tuple(message.cc),
                bcc=tuple(message.bcc),
                reply_to=tuple(message.reply_to),
                date=captured,
                # The MAILERS alias, which Django 6.1 passes to __init__.
                alias=getattr(self, "alias", None),
                size=len(raw),
                attachments=len(message.attachments),
            )
            storage.add(raw, meta)
            count += 1
        return count


def _serialise(mime: Message) -> bytes:
    """The message as bytes with CRLF line endings, so the stored ``.eml`` is RFC 5322.

    The message's own policy is kept: ``compat32`` on Django 5.2 and
    ``email.policy.default`` on 6.x produce the same 8-bit UTF-8 bodies.
    """
    buffer = BytesIO()
    policy = mime.policy.clone(linesep="\r\n")
    BytesGenerator(buffer, mangle_from_=False, policy=policy).flatten(mime)
    return buffer.getvalue()
