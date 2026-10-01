from __future__ import annotations

from email.generator import BytesGenerator
from io import BytesIO

import django
import pytest
from django.core.mail import EmailMessage, EmailMultiAlternatives

from django_mail_preview.message import BASE, Part, parse, prepare_html

PNG = b"\x89PNG\r\n\x1a\n" + bytes(range(32))
PDF = b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n"
ICS = "BEGIN:VCALENDAR\r\nVERSION:2.0\r\nEND:VCALENDAR\r\n"
HTML = "<p>Hello <b>world</b></p>"
PART_URL = "https://testserver/__mail-preview__/sent/abc/part/0/"
URLS = {"logo": PART_URL}


def serialise(message):
    """What the capture backend stores: the installed Django's output, CRLF terminated."""
    mime = message.message()
    buffer = BytesIO()
    generator = BytesGenerator(
        buffer, mangle_from_=False, policy=mime.policy.clone(linesep="\r\n")
    )
    generator.flatten(mime)
    return buffer.getvalue()


def inline_image(cid):
    """An inline PNG with a Content-ID, built the way each Django version documents it."""
    if django.VERSION >= (6, 0):
        from email.message import MIMEPart

        part = MIMEPart()
        part.set_content(
            PNG, maintype="image", subtype="png", disposition="inline", cid=f"<{cid}>"
        )
        return part
    from email.mime.image import MIMEImage

    image = MIMEImage(PNG, "png")
    image.add_header("Content-ID", f"<{cid}>")
    image.add_header("Content-Disposition", "inline")
    return image


def lines(body: str | None) -> list[str] | None:
    """A body's lines, so a trailing line break added by Django 6 doesn't matter."""
    return None if body is None else body.splitlines()


def plain(**kwargs):
    defaults = {
        "subject": "Hello",
        "body": "Hi there.",
        "from_email": "sender@example.com",
        "to": ["to@example.com"],
    }
    return EmailMessage(**{**defaults, **kwargs})


def alternatives(**kwargs):
    message = EmailMultiAlternatives(
        "Hello", "Hi there.", "sender@example.com", ["to@example.com"], **kwargs
    )
    message.attach_alternative(HTML, "text/html")
    return message


def test_plain():
    message = plain(
        cc=["cc@example.com"],
        reply_to=["reply@example.com"],
        headers={"Date": "Thu, 01 Oct 2026 12:00:00 +0000", "X-Campaign": "welcome"},
    )

    parsed = parse(serialise(message))

    assert parsed.subject == "Hello"
    assert parsed.from_ == "sender@example.com"
    assert parsed.to == "to@example.com"
    assert parsed.cc == "cc@example.com"
    assert parsed.reply_to == "reply@example.com"
    assert parsed.date == "Thu, 01 Oct 2026 12:00:00 +0000"
    assert dict(parsed.headers)["X-Campaign"] == "welcome"
    assert lines(parsed.text) == ["Hi there."]
    assert parsed.html is None
    assert parsed.parts == []


def test_headers_in_order_and_decoded():
    raw = (
        b"Received: from a\r\n"
        b"Received: from b\r\n"
        b"Subject: =?utf-8?q?Gr=C3=BC=C3=9Fe?=\r\n"
        b"\r\n"
        b"body"
    )

    parsed = parse(raw)

    assert parsed.headers == [
        ("Received", "from a"),
        ("Received", "from b"),
        ("Subject", "Grüße"),
    ]
    assert parsed.from_ == ""
    assert parsed.date == ""


def test_html_only():
    message = plain(body=HTML)
    message.content_subtype = "html"

    parsed = parse(serialise(message))

    assert lines(parsed.html) == [HTML]
    assert parsed.text is None
    assert parsed.parts == []


def test_multipart_alternative():
    parsed = parse(serialise(alternatives()))

    assert lines(parsed.text) == ["Hi there."]
    assert lines(parsed.html) == [HTML]
    assert parsed.parts == []


def test_attachments():
    message = plain()
    message.attach("report.pdf", PDF, "application/pdf")
    message.attach("notes.txt", "Some notes.", "text/plain")

    parsed = parse(serialise(message))

    assert lines(parsed.text) == ["Hi there."]
    assert parsed.html is None
    pdf, notes = parsed.parts
    assert pdf == Part(
        index=0,
        content_type="application/pdf",
        filename="report.pdf",
        content_id=None,
        size=len(PDF),
        is_inline=False,
        is_attachment=True,
        content=PDF,
    )
    assert notes.index == 1
    assert notes.content_type == "text/plain"
    assert notes.filename == "notes.txt"
    assert notes.is_attachment
    assert not notes.is_inline
    assert notes.content.splitlines() == [b"Some notes."]
    assert notes.size == len(notes.content)


def test_inline_image():
    message = alternatives()
    message.attach(inline_image("logo"))

    parsed = parse(serialise(message))

    assert lines(parsed.html) == [HTML]
    assert parsed.parts == [
        Part(
            index=0,
            content_type="image/png",
            filename=None,
            content_id="logo",
            size=len(PNG),
            is_inline=True,
            is_attachment=False,
            content=PNG,
        )
    ]


def test_extra_alternative_is_listed():
    message = alternatives()
    message.attach_alternative(ICS, "text/calendar")

    parsed = parse(serialise(message))

    assert lines(parsed.text) == ["Hi there."]
    assert lines(parsed.html) == [HTML]
    [part] = parsed.parts
    assert part.content_type == "text/calendar"
    assert part.filename is None
    assert not part.is_inline
    assert not part.is_attachment
    assert part.content.splitlines() == [
        b"BEGIN:VCALENDAR",
        b"VERSION:2.0",
        b"END:VCALENDAR",
    ]


def test_attached_message():
    message = plain(subject="Fwd: Original")
    message.attach("original.eml", plain(subject="Original"), "message/rfc822")

    parsed = parse(serialise(message))

    [part] = parsed.parts
    assert part.content_type == "message/rfc822"
    assert part.filename == "original.eml"
    assert part.is_attachment
    assert part.size == len(part.content)
    assert parse(part.content).subject == "Original"


def test_non_ascii_headers_and_filename():
    message = plain(
        subject="Grüße 🎉",
        from_email="Jürgen Müller <juergen@example.com>",
        to=["Zoë <zoe@example.com>"],
    )
    message.attach("Übersicht.pdf", PDF, "application/pdf")

    parsed = parse(serialise(message))

    assert parsed.subject == "Grüße 🎉"
    assert parsed.from_ == "Jürgen Müller <juergen@example.com>"
    assert parsed.to == "Zoë <zoe@example.com>"
    assert ("Subject", "Grüße 🎉") in parsed.headers
    assert parsed.parts[0].filename == "Übersicht.pdf"


@pytest.mark.parametrize(
    ("content_type", "body", "expected"),
    [
        ("text/plain", "héllo".encode(), "héllo"),
        ("text/plain; charset=x-unknown", "héllo".encode(), "héllo"),
        ("text/plain; charset=iso-8859-1", "héllo".encode("latin-1"), "héllo"),
        ("text/plain; charset=utf-8", b"h\xffllo", "h�llo"),
    ],
)
def test_text_decoding(content_type, body, expected):
    raw = b"Content-Type: " + content_type.encode() + b"\r\n\r\n" + body

    parsed = parse(raw)

    assert parsed.text == expected


def test_empty_body():
    parsed = parse(serialise(plain(body="")))

    assert parsed.text is not None
    assert parsed.text.strip() == ""
    assert parsed.html is None
    assert parsed.parts == []


def test_source_of_a_django_message():
    raw = serialise(plain())

    parsed = parse(raw)

    assert b"\r\n" in raw
    assert parsed.source == raw.decode().replace("\r\n", "\n")


def test_source_replaces_invalid_bytes():
    raw = (
        b"Subject: Hi\r\nContent-Type: text/plain; charset=utf-8\r\n\r\nh\xffllo\r\nbye"
    )

    parsed = parse(raw)

    assert parsed.source == (
        "Subject: Hi\nContent-Type: text/plain; charset=utf-8\n\nh�llo\nbye"
    )


@pytest.mark.parametrize(
    ("html", "expected"),
    [
        ('<img src="cid:logo">', f'<img src="{PART_URL}">'),
        ("<img src='cid:logo'>", f"<img src='{PART_URL}'>"),
        ("<img src=cid:logo>", f"<img src={PART_URL}>"),
        (
            '<td style="background: url(cid:logo)">',
            f'<td style="background: url({PART_URL})">',
        ),
        (
            "<style>body { background: url('cid:logo') }</style>",
            f"<style>body {{ background: url('{PART_URL}') }}</style>",
        ),
        ('<img src="cid:unknown">', '<img src="cid:unknown">'),
        ("<p>Write to cid:logo</p>", "<p>Write to cid:logo</p>"),
    ],
)
def test_prepare_html_rewrites_cid_references(html, expected):
    result = prepare_html(html, URLS.get)

    assert result == BASE + expected


def test_prepare_html_rewrites_every_reference():
    html = '<img src="cid:logo"><img src="cid:logo"><img src="cid:other">'

    result = prepare_html(html, URLS.get)

    assert result.count(PART_URL) == 2
    assert 'src="cid:other"' in result


@pytest.mark.parametrize(
    ("html", "expected"),
    [
        (
            "<html><head><title>x</title></head><body></body></html>",
            f"<html><head>{BASE}<title>x</title></head><body></body></html>",
        ),
        (
            '<HTML><HEAD lang="en">\n<title>x</title></HEAD></HTML>',
            f'<HTML><HEAD lang="en">{BASE}\n<title>x</title></HEAD></HTML>',
        ),
        ("<p>No head</p>", f"{BASE}<p>No head</p>"),
        ("<header>Not a head</header>", f"{BASE}<header>Not a head</header>"),
    ],
)
def test_prepare_html_injects_base(html, expected):
    result = prepare_html(html, URLS.get)

    assert result == expected
