"""Storage of captured messages: the raw bytes plus a metadata record per message.

``FileStorage`` keeps one ``.eml`` and one ``.json`` file per message under
``MAIL_PREVIEW_ROOT``. Another ``BaseStorage`` subclass can take its place
through ``MAIL_PREVIEW_STORAGE``.
"""

from __future__ import annotations

import inspect
import json
import os
import re
import uuid
from abc import ABC, abstractmethod
from collections.abc import Callable, Iterator
from contextlib import suppress
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from functools import cached_property
from pathlib import Path
from typing import Any

from django.core.exceptions import ImproperlyConfigured
from django.utils.module_loading import import_string

from django_mail_preview.conf import mail_preview_settings

__all__ = [
    "FILES",
    "MESSAGE_ID",
    "BaseStorage",
    "FileStorage",
    "MessageMeta",
    "StoredMessage",
    "get_storage",
    "new_id",
    "storage_class",
]

MESSAGE_ID = r"[0-9]{8}-[0-9]{6}-[0-9]{6}-[0-9a-f]{8}"
"""Regex of a message id, for the URLconf: UTC capture time, then eight hex characters."""

FILES = "files"
"""The ``MAIL_PREVIEW_STORAGE`` value that selects ``FileStorage``."""


def new_id(captured: datetime) -> str:
    """A message id: the capture time in UTC to the microsecond, then eight hex characters of a UUID.

    Ids sort chronologically by name and are safe in URLs and file names.
    """
    utc = captured.astimezone(timezone.utc)
    return f"{utc:%Y%m%d-%H%M%S-%f}-{uuid.uuid4().hex[:8]}"


@dataclass(frozen=True)
class MessageMeta:
    """What the inbox lists about a message; also the JSON sidecar of the file storage.

    ``bcc`` is kept here because the serialised message doesn't contain it.
    """

    id: str
    subject: str
    from_email: str
    to: tuple[str, ...]
    cc: tuple[str, ...]
    bcc: tuple[str, ...]
    reply_to: tuple[str, ...]
    date: datetime
    """Capture time, timezone-aware."""
    alias: str | None
    """The ``MAILERS`` alias the message was sent through; ``None`` before Django 6.1."""
    size: int
    """Bytes of the serialised message."""
    attachments: int
    tags: tuple[str, ...] = ()
    """Fixed at capture: from the ``X-Tags`` header, the ``MAIL_PREVIEW_TAGS`` function and plus addressing."""

    def to_json(self) -> str:
        return json.dumps({**asdict(self), "date": self.date.isoformat()})

    @classmethod
    def from_json(cls, text: str) -> MessageMeta:
        data: dict[str, Any] = json.loads(text)
        return cls(
            id=data["id"],
            subject=data["subject"],
            from_email=data["from_email"],
            to=tuple(data["to"]),
            cc=tuple(data["cc"]),
            bcc=tuple(data["bcc"]),
            reply_to=tuple(data["reply_to"]),
            date=datetime.fromisoformat(data["date"]),
            alias=data["alias"],
            size=data["size"],
            attachments=data["attachments"],
            # A sidecar written before tags existed has none.
            tags=tuple(data.get("tags", ())),
        )


class StoredMessage:
    """A captured message: its metadata, and its bytes read on first access.

    ``raw`` is ``None`` when the bytes are gone, for example deleted between
    listing and reading, so the inbox can answer 404 instead of raising.
    """

    def __init__(self, meta: MessageMeta, load: Callable[[], bytes | None]) -> None:
        self.meta = meta
        self._load = load

    @cached_property
    def raw(self) -> bytes | None:
        return self._load()


class BaseStorage(ABC):
    """Where captured messages live.

    Subclasses are constructed without arguments, on every use, so they read
    their configuration from settings rather than caching it at import time.
    """

    @abstractmethod
    def add(self, raw: bytes, meta: MessageMeta) -> None:
        """Store a message."""

    @abstractmethod
    def get(self, id: str) -> StoredMessage | None:
        """One message, or ``None`` when the id is unknown or the message is gone."""

    @abstractmethod
    def list(self) -> list[StoredMessage]:
        """Every message, newest first."""

    @abstractmethod
    def delete(self, id: str) -> None:
        """Delete one message; silent when it's missing."""

    @abstractmethod
    def clear(self) -> None:
        """Delete every message."""


class FileStorage(BaseStorage):
    """One ``<id>.eml`` and one ``<id>.json`` per message under ``MAIL_PREVIEW_ROOT``.

    The directory listing is the index, so there is no index to corrupt and
    parallel sends from threads or processes can't lose each other's mail.
    """

    def __init__(self) -> None:
        self.root = Path(mail_preview_settings.ROOT).resolve()
        self.max_messages = mail_preview_settings.MAX_MESSAGES

    def add(self, raw: bytes, meta: MessageMeta) -> None:
        # /tmp is shared between users on Linux, so keep the mail private.
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self._write(self._path(meta.id, ".eml"), raw)
        # The .json is the index entry, written last so a listing never sees a
        # message without its bytes.
        self._write(self._path(meta.id, ".json"), meta.to_json().encode())
        self._apply_retention()

    def get(self, id: str) -> StoredMessage | None:
        return self._read(self._path(id, ".json"))

    def list(self) -> list[StoredMessage]:
        paths = sorted(self._index(), key=lambda path: path.name, reverse=True)
        messages = (self._read(path) for path in paths)
        # A message deleted between listing and reading is simply gone.
        return [message for message in messages if message is not None]

    def delete(self, id: str) -> None:
        # The .json goes first, so the message leaves the index before its bytes.
        self._path(id, ".json").unlink(missing_ok=True)
        self._path(id, ".eml").unlink(missing_ok=True)

    def clear(self) -> None:
        for pattern in ("*.json", "*.eml", "*.tmp"):
            for path in self.root.glob(pattern):
                path.unlink(missing_ok=True)

    def _index(self) -> Iterator[Path]:
        """The ``.json`` files of the stored messages, whatever else is in the directory."""
        return (
            path
            for path in self.root.glob("*.json")
            if re.fullmatch(MESSAGE_ID, path.stem)
        )

    def _path(self, id: str, suffix: str) -> Path:
        return self.root / f"{id}{suffix}"

    def _read(self, path: Path) -> StoredMessage | None:
        try:
            meta = MessageMeta.from_json(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        return StoredMessage(meta, lambda: self._load(meta.id))

    def _load(self, id: str) -> bytes | None:
        try:
            return self._path(id, ".eml").read_bytes()
        except FileNotFoundError:
            return None

    def _write(self, path: Path, data: bytes) -> None:
        """Write to a temporary file, then move it into place, so readers see all or nothing."""
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_bytes(data)
        os.replace(tmp, path)

    def _apply_retention(self) -> None:
        """Drop the oldest messages beyond ``MAX_MESSAGES``.

        Best-effort: an ``OSError`` means another process got there first, or
        Windows still has the file open, and must not fail the send.
        """
        ids = sorted(path.stem for path in self._index())
        for id in ids[: max(len(ids) - self.max_messages, 0)]:
            with suppress(OSError):
                self.delete(id)


def storage_class(path: str) -> type[BaseStorage]:
    """The storage class a ``MAIL_PREVIEW_STORAGE`` value names.

    Raises ``ImproperlyConfigured`` when the dotted path doesn't import or
    doesn't name a concrete ``BaseStorage`` subclass.
    """
    if path == FILES:
        return FileStorage
    try:
        cls: object = import_string(path)
    except ImportError as error:
        raise ImproperlyConfigured(str(error)) from error
    if not (isinstance(cls, type) and issubclass(cls, BaseStorage)):
        raise ImproperlyConfigured(f"{path!r} is not a BaseStorage subclass.")
    if inspect.isabstract(cls):
        raise ImproperlyConfigured(f"{path!r} is abstract.")
    return cls


def get_storage() -> BaseStorage:
    """The configured storage, built on every call so settings overrides take effect."""
    return storage_class(mail_preview_settings.STORAGE)()
