# Inbox

The inbox shows the mail your app sent through the capture backend.

## What is captured

Every message sent through the capture backend is stored, whatever sends it:
`send_mail()`, `EmailMessage.send()`, `mail_admins()`, a password-reset form. The
backend builds the MIME message once, as the SMTP backend would, so a message with an
invalid header raises at send time just as it would in production, and the stored
message carries the `Message-ID` and `Date` headers Django adds.

The stored bytes are the message as a mail server would get it, with CRLF line
endings, so the `.eml` opens in Apple Mail, Outlook or Thunderbird. `Bcc` is kept with
the message's metadata, because it's never part of the serialised message.

Mail your test suite sends isn't captured. Django's test runner swaps in the in-memory
backend for the whole run, so `mail.outbox` works as before. See [Limits](limits.md).

## The page

The sidebar lists the previews grouped by app, then the captured messages newest
first under "Inbox" with their count. The start page shows the captured mail as a
table with the subject, sender, recipients, an attachment count, the size and the
time. On a phone the sidebar sits behind a Menu button.

A message page shows the subject, the sender and recipients, the capture time and, on
Django 6.1, the `MAILERS` alias the message went through. Tabs:

- HTML: the HTML part in a sandboxed frame. The toolbar sets the frame's width, 320,
  375, 600 (the common email width) or 768 pixels, full width, or any number you
  type. The choice is remembered. "Open in new tab" shows the HTML on its own.
- Plain text: the text part, with a Copy button.
- Source: the raw message, with a Copy button. It loads as its own page, because
  attachments make it large.
- Headers: every header, decoded.
- MIME: the message's structure as a tree, one line per part with its content type,
  disposition, filename and decoded size.

Under the tabs, "Parts" lists everything that isn't one of the two bodies, so nothing
in a message stays hidden: attachments, inline images and extra alternatives such as
`text/calendar`, each with a download link.

The Newer and Older buttons in the header move through the list, and so do the `k`
and `j` keys. On the start page `j` and `k` move through the table and Enter opens the
focused row.

The Download button saves the message as `<id>.eml`. The file is the message as
stored, so a desktop mail client opens it. That's the closest you get to seeing the
message in a real client without sending it.

## New mail while the page is open

The page polls for new mail every three seconds while its tab is visible. On the
start page, new mail reloads the list. With a message open, a "New mail" badge appears
in the sidebar instead, and the number of messages that arrived since the page loaded
shows in the tab's title and on the favicon.

## Deleting

The Delete button on a message page removes that message, and "Clear all" in the
sidebar removes every captured message. Both ask first. There is no undo, since
captured mail is disposable developer state.

## Storage

Messages are stored as files, one `<id>.eml` and one `<id>.json` per message, under
`MAIL_PREVIEW_ROOT`. The directory listing is the index, so there is no index file to
corrupt, and parallel sends from several threads or processes can't lose each other's
mail. Each file is written under a temporary name and moved into place, so a listing
never sees a half-written message.

By default the directory is under the system temp dir, named after a hash of
`BASE_DIR`, so projects on one machine get separate inboxes without configuration. The
start page names the directory while the inbox is empty, and the Inbox heading in the
sidebar shows it in a tooltip. Set
[`MAIL_PREVIEW_ROOT`](settings.md#mail_preview_root) to choose the directory, for
example on a volume shared between containers (see
[Docker and several processes](installation.md#docker-and-several-processes)).

The directory is created on first write with permissions that keep the mail private
to your user, because `/tmp` is shared between users on Linux.

### Retention

After every send, the oldest messages beyond
[`MAIL_PREVIEW_MAX_MESSAGES`](settings.md#mail_preview_max_messages) are deleted, 100
by default. Retention never fails a send: when another process deleted a file first,
or Windows still has it open, the error is ignored.

Message ids are the UTC capture time to the microsecond followed by eight random hex
characters, `20261002-143015-123456-9f8e7d6c` for example, so they sort
chronologically and are safe in URLs and file names.

### Your own storage

[`MAIL_PREVIEW_STORAGE`](settings.md#mail_preview_storage) names a `BaseStorage`
subclass to use instead of the file storage:

```python
MAIL_PREVIEW_STORAGE = "myproject.mail_storage.RedisStorage"
```

A storage implements five methods. It's constructed without arguments on every use,
so it should read its configuration from settings rather than cache it:

```python
from django_mail_preview.storage import BaseStorage, MessageMeta, StoredMessage


class RedisStorage(BaseStorage):
    def add(self, raw: bytes, meta: MessageMeta) -> None: ...

    def get(self, id: str) -> StoredMessage | None: ...

    def list(self) -> list[StoredMessage]: ...

    def delete(self, id: str) -> None: ...

    def clear(self) -> None: ...
```

`list()` returns the messages newest first. `get()` returns `None` for an unknown id,
and `delete()` is silent when the id is missing. A `StoredMessage` wraps the
`MessageMeta` and a loader for the raw bytes; the loader returns `None` when the bytes
are gone, so the page answers 404 instead of raising. `MessageMeta.to_json()` and
`MessageMeta.from_json()` serialise the metadata. See the
[API reference](api.md#storage).

The system check `django_mail_preview.E002` reports a path that doesn't import or
doesn't name a concrete `BaseStorage` subclass.
