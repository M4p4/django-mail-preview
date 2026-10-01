"""Parsing of a stored message into what the inbox and preview pages show.

Pure stdlib: ``email`` parses what every supported Django version serialises,
legacy MIME on 5.2 and the modern API on 6.x alike.
"""

from __future__ import annotations

import email
import email.policy
import re
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from email.message import EmailMessage, MIMEPart

__all__ = ["ParsedMessage", "Part", "parse", "prepare_html"]

CID = re.compile(r"""(?<=["'(=])cid:([^"'\s()<>]+)""")
"""A ``cid:`` reference in an attribute value or a CSS ``url()``, capturing the id."""

HEAD = re.compile(r"<head\b[^>]*>", re.IGNORECASE)

BASE = '<base target="_blank">'


@dataclass(frozen=True)
class Part:
    """A part of a message other than its text and HTML bodies.

    Attachments, inline images and extra alternatives such as ``text/calendar``
    all end up here, so nothing in a message stays hidden.
    """

    index: int
    """Position in ``ParsedMessage.parts``; the part URLs use it."""
    content_type: str
    filename: str | None
    content_id: str | None
    """The ``Content-ID`` without its angle brackets, as ``cid:`` references use it."""
    size: int
    is_inline: bool
    """Whether the part has a ``Content-ID``, so the HTML body can reference it."""
    is_attachment: bool
    """Whether the disposition is ``attachment`` or the part has a filename."""
    content: bytes = field(repr=False)


@dataclass(frozen=True)
class ParsedMessage:
    headers: list[tuple[str, str]]
    """Every header in order, decoded."""
    subject: str
    from_: str
    to: str
    cc: str
    reply_to: str
    date: str
    html: str | None
    text: str | None
    parts: list[Part]
    source: str
    """The raw message decoded for display, with CRLF normalised to LF."""


def parse(raw: bytes) -> ParsedMessage:
    """Parse the stored bytes of a message."""
    message = email.message_from_bytes(raw, policy=email.policy.default)
    # The default policy builds EmailMessage objects; narrow the typed Message once.
    assert isinstance(message, EmailMessage)
    html = message.get_body(("html",))
    text = message.get_body(("plain",))
    leaves = [
        leaf for leaf in _leaves(message) if leaf is not html and leaf is not text
    ]
    parts = [_part(index, leaf) for index, leaf in enumerate(leaves)]
    return ParsedMessage(
        headers=[(name, str(value)) for name, value in message.items()],
        subject=_header(message, "Subject"),
        from_=_header(message, "From"),
        to=_header(message, "To"),
        cc=_header(message, "Cc"),
        reply_to=_header(message, "Reply-To"),
        date=_header(message, "Date"),
        html=None if html is None else _text(html),
        text=None if text is None else _text(text),
        parts=parts,
        source=raw.decode("utf-8", errors="replace").replace("\r\n", "\n"),
    )


def prepare_html(html: str, part_url: Callable[[str], str | None]) -> str:
    """Prepare an HTML body for the frame it is served into.

    ``cid:`` references in attribute values and CSS ``url()`` are replaced with
    the URL ``part_url`` returns for the id, which must be absolute (a ``data:``
    URI is) so the email's own ``<base href>`` can't redirect them; unknown ids
    stay as they are. ``<base target="_blank">`` is injected right after ``<head>``, or at the
    top when there is none, so links open in a new tab instead of navigating the
    frame.
    """

    def replace(match: re.Match[str]) -> str:
        url = part_url(match[1])
        return match[0] if url is None else url

    html = CID.sub(replace, html)
    head = HEAD.search(html)
    if head is None:
        return BASE + html
    return html[: head.end()] + BASE + html[head.end() :]


def _leaves(part: MIMEPart) -> Iterator[MIMEPart]:
    """Every non-multipart part, in order; an attached message counts as one part."""
    if part.get_content_maintype() == "multipart":
        for subpart in part.iter_parts():
            yield from _leaves(subpart)
    else:
        yield part


def _part(index: int, part: MIMEPart) -> Part:
    content = _content(part)
    filename = part.get_filename()
    content_id = part.get("Content-ID")
    return Part(
        index=index,
        content_type=part.get_content_type(),
        filename=filename,
        content_id=None if content_id is None else str(content_id).strip("<>"),
        size=len(content),
        is_inline=content_id is not None,
        is_attachment=part.get_content_disposition() == "attachment"
        or filename is not None,
        content=content,
    )


def _content(part: MIMEPart) -> bytes:
    payload = part.get_payload(decode=True)
    if isinstance(payload, bytes):
        return payload
    # A message/rfc822 part holds the attached message instead of encoded bytes.
    attached = part.get_payload(0)
    assert isinstance(attached, EmailMessage)
    return attached.as_bytes()


def _text(part: MIMEPart) -> str:
    """Decode a text part; a missing or unknown charset is read as UTF-8."""
    content = _content(part)
    charset = part.get_content_charset() or "utf-8"
    try:
        return content.decode(charset, errors="replace")
    except LookupError:
        return content.decode("utf-8", errors="replace")


def _header(message: EmailMessage, name: str) -> str:
    return str(message.get(name, ""))
