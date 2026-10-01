from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import django
import pytest
from django.core import mail
from django.core.mail import EmailMessage, send_mail

from django_mail_preview.backends import EmailBackend
from django_mail_preview.checks import BACKEND
from django_mail_preview.storage import MESSAGE_ID, FileStorage

# Django 6.1 deprecates EMAIL_BACKEND and get_connection() for MAILERS and
# mail.mailers; a deprecation warning is an error in this suite.
MAILERS = django.VERSION >= (6, 1)
PDF = b"%PDF-1.7\n"


def plain(**kwargs):
    defaults = {
        "subject": "Hello",
        "body": "Hi there.",
        "from_email": "sender@example.com",
        "to": ["to@example.com"],
    }
    return EmailMessage(**{**defaults, **kwargs})


@pytest.fixture
def route(settings):
    """Configure the capture backend the way the installed Django documents it.

    Returns the keyword arguments that send through it.
    """
    if MAILERS:
        settings.MAILERS = {"default": {"BACKEND": BACKEND}}
        return {"using": "default"}
    settings.EMAIL_BACKEND = BACKEND
    return {}


@pytest.fixture
def connection(route):
    """A connection to the configured capture backend."""
    if MAILERS:
        return mail.mailers["default"]
    return mail.get_connection()


def stored():
    return FileStorage().list()


def test_send_messages_stores_each():
    backend = EmailBackend()

    count = backend.send_messages([plain(subject="One"), plain(subject="Two")])

    assert count == 2
    assert [message.meta.subject for message in stored()] == ["Two", "One"]


def test_empty_input():
    backend = EmailBackend()

    count = backend.send_messages([])

    assert count == 0
    assert stored() == []


def test_connection_through_the_configured_route(connection):
    count = connection.send_messages([plain()])

    assert isinstance(connection, EmailBackend)
    assert count == 1
    assert [message.meta.subject for message in stored()] == ["Hello"]


def test_send_mail_through_the_configured_route(route):
    count = send_mail("Hello", "Hi.", "sender@example.com", ["to@example.com"], **route)

    assert count == 1
    [message] = stored()
    assert message.meta.subject == "Hello"
    assert message.meta.to == ("to@example.com",)
    assert message.meta.alias == ("default" if MAILERS else None)


def test_metadata():
    message = plain(
        subject="Grüße",
        cc=["cc@example.com"],
        bcc=["bcc@example.com"],
        reply_to=["reply@example.com"],
    )
    message.attach("report.pdf", PDF, "application/pdf")
    message.attach("notes.txt", "Some notes.", "text/plain")
    before = datetime.now(timezone.utc)

    EmailBackend().send_messages([message])

    [captured] = stored()
    meta = captured.meta
    assert re.fullmatch(MESSAGE_ID, meta.id)
    assert meta.id.startswith(f"{meta.date:%Y%m%d-%H%M%S-%f}")
    assert before <= meta.date <= before + timedelta(seconds=10)
    assert meta.subject == "Grüße"
    assert meta.from_email == "sender@example.com"
    assert meta.to == ("to@example.com",)
    assert meta.cc == ("cc@example.com",)
    assert meta.bcc == ("bcc@example.com",)
    assert meta.reply_to == ("reply@example.com",)
    assert meta.alias is None
    assert meta.size == len(captured.raw)
    assert meta.attachments == 2
    assert b"bcc@example.com" not in captured.raw


@pytest.mark.skipif(not MAILERS, reason="MAILERS arrived in Django 6.1")
def test_alias_is_recorded(settings):
    settings.MAILERS = {"dev": {"BACKEND": BACKEND}}

    mail.mailers["dev"].send_messages([plain()])

    [message] = stored()
    assert message.meta.alias == "dev"


def test_message_id_is_minted_once():
    EmailBackend().send_messages([plain()])

    [message] = stored()
    assert message.raw.count(b"Message-ID:") == 1


def test_stored_bytes_use_crlf():
    message = plain(body="Line one.\nLine two.\n")
    message.attach("notes.txt", "A\nB\n", "text/plain")

    EmailBackend().send_messages([message])

    [captured] = stored()
    assert b"\r\n" in captured.raw
    assert b"\n" not in captured.raw.replace(b"\r\n", b"")
    assert b"Line one.\r\nLine two." in captured.raw


def test_header_validation_error_propagates():
    backend = EmailBackend()

    with pytest.raises(ValueError):
        backend.send_messages([plain(subject="Hi\nthere")])

    assert stored() == []


def test_fail_silently_is_accepted_and_ignored(settings, tmp_path):
    (tmp_path / "file").write_text("")
    settings.MAIL_PREVIEW_ROOT = tmp_path / "file" / "inbox"
    backend = EmailBackend(fail_silently=True)

    with pytest.raises(OSError):
        backend.send_messages([plain()])


def test_parallel_sends_lose_nothing(mail_preview_root):
    backend = EmailBackend()
    messages = [plain(subject=f"Message {n}") for n in range(50)]

    with ThreadPoolExecutor(max_workers=8) as pool:
        counts = list(
            pool.map(lambda message: backend.send_messages([message]), messages)
        )

    captured = stored()
    assert counts == [1] * 50
    assert len({message.meta.id for message in captured}) == 50
    assert sorted(message.meta.subject for message in captured) == sorted(
        message.subject for message in messages
    )
    assert all(message.raw is not None for message in captured)
    assert list(mail_preview_root.glob("*.tmp")) == []
