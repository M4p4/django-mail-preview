from __future__ import annotations

import json
import re
import stat
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from django.core.exceptions import ImproperlyConfigured
from django.test import override_settings

from django_mail_preview.storage import (
    MESSAGE_ID,
    BaseStorage,
    FileStorage,
    MessageMeta,
    StoredMessage,
    get_storage,
    new_id,
)

CAPTURED = datetime(2026, 10, 1, 12, 0, 0, 123456, tzinfo=timezone.utc)
RAW = b"Subject: Hello\r\n\r\nHi there.\r\n"

posix_only = pytest.mark.skipif(sys.platform == "win32", reason="POSIX file system")


class MemoryStorage(BaseStorage):
    """A complete storage at a dotted path, for MAIL_PREVIEW_STORAGE."""

    messages: dict[str, tuple[bytes, MessageMeta]] = {}

    def add(self, raw, meta):
        self.messages[meta.id] = (raw, meta)

    def get(self, id):
        if id not in self.messages:
            return None
        raw, meta = self.messages[id]
        return StoredMessage(meta, lambda: raw)

    def list(self):
        return [self.get(id) for id in sorted(self.messages, reverse=True)]

    def delete(self, id):
        self.messages.pop(id, None)

    def clear(self):
        self.messages.clear()


class NotAStorage:
    """A class at a dotted path that isn't a storage."""


def meta(captured=CAPTURED, **kwargs):
    defaults = {
        "id": new_id(captured),
        "subject": "Hello",
        "from_email": "sender@example.com",
        "to": ("to@example.com",),
        "cc": (),
        "bcc": ("bcc@example.com",),
        "reply_to": (),
        "date": captured,
        "alias": None,
        "size": len(RAW),
        "attachments": 0,
    }
    return MessageMeta(**{**defaults, **kwargs})


def add(storage, captured=CAPTURED):
    """Store a message captured at ``captured`` and return its metadata."""
    record = meta(captured)
    storage.add(RAW, record)
    return record


def ids(messages):
    return [message.meta.id for message in messages]


@pytest.mark.parametrize(
    "captured",
    [
        CAPTURED,
        # The same instant, two hours east.
        datetime(2026, 10, 1, 14, 0, 0, 123456, tzinfo=timezone(timedelta(hours=2))),
    ],
)
def test_new_id(captured):
    id = new_id(captured)

    assert re.fullmatch(MESSAGE_ID, id)
    assert id.startswith("20261001-120000-123456-")


def test_new_ids_differ():
    one = new_id(CAPTURED)
    two = new_id(CAPTURED)

    assert one != two


@pytest.mark.parametrize(
    "value",
    [
        "clear",
        "latest",
        "20261001-120000-123456-0123ABCD",
        "20261001-120000-123456-0123abc",
        "20261001-120000-123456-0123abcd/",
        "../20261001-120000-123456-0123abcd",
    ],
)
def test_message_id_pattern_rejects(value):
    assert re.fullmatch(MESSAGE_ID, value) is None


def test_meta_json_round_trip():
    record = meta(
        alias="dev",
        attachments=2,
        cc=("cc@example.com",),
        tags=("billing", "onboarding"),
    )

    text = record.to_json()
    restored = MessageMeta.from_json(text)

    assert restored == record
    data = json.loads(text)
    assert data["date"] == "2026-10-01T12:00:00.123456+00:00"
    assert data["to"] == ["to@example.com"]
    assert data["alias"] == "dev"
    assert data["tags"] == ["billing", "onboarding"]


def test_meta_from_json_without_tags():
    """A sidecar written before tags existed loads as untagged."""
    record = meta()
    data = json.loads(record.to_json())
    del data["tags"]

    restored = MessageMeta.from_json(json.dumps(data))

    assert restored == record
    assert restored.tags == ()


def test_round_trip(mail_preview_root):
    storage = FileStorage()
    record = meta()

    storage.add(RAW, record)
    stored = storage.get(record.id)

    assert stored is not None
    assert stored.meta == record
    assert stored.raw == RAW
    assert sorted(path.name for path in mail_preview_root.iterdir()) == [
        f"{record.id}.eml",
        f"{record.id}.json",
    ]


def test_get_unknown():
    storage = FileStorage()

    stored = storage.get(new_id(CAPTURED))

    assert stored is None


def test_without_directory(settings, tmp_path):
    settings.MAIL_PREVIEW_ROOT = tmp_path / "missing"
    storage = FileStorage()

    messages = storage.list()
    storage.clear()
    storage.delete(new_id(CAPTURED))

    assert messages == []
    assert not (tmp_path / "missing").exists()


def test_list_newest_first():
    storage = FileStorage()
    first = add(storage, CAPTURED)
    second = add(storage, CAPTURED + timedelta(seconds=1))
    third = add(storage, CAPTURED + timedelta(microseconds=1))

    messages = storage.list()

    assert ids(messages) == [second.id, third.id, first.id]


def test_list_skips_other_files(mail_preview_root):
    storage = FileStorage()
    record = add(storage)
    (mail_preview_root / "notes.json").write_text("{}")
    (mail_preview_root / f"{new_id(CAPTURED)}.eml.tmp").write_bytes(RAW)
    (mail_preview_root / f"{new_id(CAPTURED)}.json.tmp").write_bytes(b"{")

    messages = storage.list()

    assert ids(messages) == [record.id]


@posix_only
def test_list_skips_a_message_deleted_meanwhile(mail_preview_root):
    storage = FileStorage()
    record = add(storage)
    # A dangling link stands in for a .json deleted between listing and reading.
    link = mail_preview_root / f"{new_id(CAPTURED + timedelta(seconds=1))}.json"
    link.symlink_to(mail_preview_root / "gone.json")

    messages = storage.list()

    assert ids(messages) == [record.id]


def test_delete(mail_preview_root):
    storage = FileStorage()
    record = add(storage)
    other = add(storage, CAPTURED + timedelta(seconds=1))

    storage.delete(record.id)

    assert storage.get(record.id) is None
    assert ids(storage.list()) == [other.id]
    assert list(mail_preview_root.glob(f"{record.id}.*")) == []


def test_delete_missing_is_silent():
    storage = FileStorage()
    record = add(storage)

    storage.delete(new_id(CAPTURED))

    assert ids(storage.list()) == [record.id]


def test_clear(mail_preview_root):
    storage = FileStorage()
    add(storage)
    add(storage, CAPTURED + timedelta(seconds=1))
    (mail_preview_root / f"{new_id(CAPTURED)}.eml.tmp").write_bytes(RAW)
    (mail_preview_root / "keep.txt").write_text("")

    storage.clear()

    assert storage.list() == []
    assert [path.name for path in mail_preview_root.iterdir()] == ["keep.txt"]


def test_raw_is_none_when_the_bytes_are_gone(mail_preview_root):
    storage = FileStorage()
    record = add(storage)
    [message] = storage.list()
    (mail_preview_root / f"{record.id}.eml").unlink()

    raw = message.raw

    assert raw is None


def test_raw_is_read_once(mail_preview_root):
    storage = FileStorage()
    record = add(storage)
    message = storage.get(record.id)
    assert message is not None
    assert message.raw == RAW
    (mail_preview_root / f"{record.id}.eml").unlink()

    raw = message.raw

    assert raw == RAW


@pytest.mark.parametrize(("max_messages", "kept"), [(1, 1), (2, 2), (3, 3), (4, 3)])
def test_retention(settings, mail_preview_root, max_messages, kept):
    settings.MAIL_PREVIEW_MAX_MESSAGES = max_messages
    storage = FileStorage()
    records = [add(storage, CAPTURED + timedelta(seconds=n)) for n in range(3)]

    messages = storage.list()

    assert ids(messages) == [record.id for record in reversed(records)][:kept]
    assert len(list(mail_preview_root.iterdir())) == 2 * kept


def test_retention_tolerates_an_os_error(settings, monkeypatch):
    settings.MAIL_PREVIEW_MAX_MESSAGES = 1
    storage = FileStorage()
    first = add(storage)

    def delete(self, id):
        # Another process got there first, or Windows has the file open.
        raise PermissionError(id)

    monkeypatch.setattr(FileStorage, "delete", delete)

    second = add(storage, CAPTURED + timedelta(seconds=1))

    assert ids(storage.list()) == [second.id, first.id]


@posix_only
def test_root_is_private(settings, tmp_path):
    settings.MAIL_PREVIEW_ROOT = tmp_path / "inbox"
    storage = FileStorage()

    add(storage)

    assert stat.S_IMODE((tmp_path / "inbox").stat().st_mode) == 0o700


@pytest.mark.parametrize("convert", [str, Path])
def test_root_is_resolved(settings, tmp_path, monkeypatch, convert):
    monkeypatch.chdir(tmp_path)
    settings.MAIL_PREVIEW_ROOT = convert("inbox")

    storage = FileStorage()

    assert storage.root == (tmp_path / "inbox").resolve()


@pytest.mark.parametrize(
    ("path", "cls"),
    [
        ("files", FileStorage),
        ("django_mail_preview.storage.FileStorage", FileStorage),
        ("tests.test_storage.MemoryStorage", MemoryStorage),
    ],
)
def test_get_storage(path, cls):
    with override_settings(MAIL_PREVIEW_STORAGE=path):
        storage = get_storage()

    assert type(storage) is cls


@pytest.mark.parametrize(
    "path",
    [
        "missing.module.Storage",
        "tests.test_storage.missing",
        "tests.test_storage.NotAStorage",
        "tests.test_storage.meta",
        "django_mail_preview.storage.BaseStorage",
        "FileStorage",
    ],
)
def test_get_storage_invalid(path):
    with (
        override_settings(MAIL_PREVIEW_STORAGE=path),
        pytest.raises(ImproperlyConfigured),
    ):
        get_storage()


def test_custom_storage_is_used_as_is():
    with override_settings(MAIL_PREVIEW_STORAGE="tests.test_storage.MemoryStorage"):
        storage = get_storage()
        first = add(storage)
        second = add(storage, CAPTURED + timedelta(seconds=1))
        listed = ids(storage.list())
        storage.delete(first.id)
        storage.delete(first.id)
        after_delete = ids(storage.list())
        stored = storage.get(second.id)
        storage.clear()
        after_clear = storage.list()

    assert listed == [second.id, first.id]
    assert after_delete == [second.id]
    assert stored is not None
    assert stored.raw == RAW
    assert storage.get(first.id) is None
    assert after_clear == []
