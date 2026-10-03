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
time. While nothing is captured it shows the one command that changes that: the
setting that points the project at the capture backend, or, once that is active, a
`manage.py shell` one-liner that sends a message. A project without previews gets a
link to the [previews guide](previews.md). On a phone the sidebar sits behind a Menu
button.

The pages follow the system's light or dark scheme until you press the sun or moon
button beside the name, in the sidebar or in a phone's top bar. The choice is kept in
the browser and applied before the page paints, so the next load doesn't flash. The
email in the frame is not affected: it keeps the system's scheme, as a mail client on
the same machine would show it.

A message page shows the subject, the sender and recipients, the capture time and, on
Django 6.1, the `MAILERS` alias the message went through. Tabs:

- HTML: the HTML part in a sandboxed frame. The toolbar sets the frame's width: 375
  pixels, 600 pixels (the common email width), full width, or any number you type.
  The choice is remembered. "Open in new tab" shows the HTML on its own.
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

## Searching

The box beside the Inbox heading filters the table as you type. A word matches the
subject, the sender and the recipients; `from:`, `to:` and `subject:` narrow a word
to one field; `has:attachment` keeps the messages with attachments; `tag:` keeps the
messages with that [tag](#tagging-mail); a leading `-` excludes. So
`invoice -from:billing@` is every message about an invoice that billing didn't send,
and `tag:billing -has:attachment` every billing message without an attachment. Terms
match anywhere in the text, case apart, and all of them must match; a `tag:` term
names a whole tag, so `tag:bill` doesn't find `billing`. The heading shows how many
messages match, and the query stays in the URL, so a reload keeps it. `/` focuses the
box from any page and Escape clears it.

The filter runs in the browser over the messages the page lists, so it covers at
most [`MAIL_PREVIEW_MAX_MESSAGES`](settings.md#mail_preview_max_messages).

## Tagging mail

A captured message can carry tags. They show as chips under the subject in the table,
on the sidebar rows and on the message page, and a row under the Inbox heading lists
every tag with how many messages carry it. The lists show the first few chips, three
in the table and two in the sidebar, then a count whose tooltip names the rest; the
message page shows them all. Clicking a chip filters the table through
the search box (`tag:billing`), and the chips on a message page link to the inbox
filtered the same way.

Tags come from three sources, merged:

- The message's `X-Tags` header, comma separated. It's the header
  [Mailpit](https://mailpit.axllent.org/docs/usage/tagging/) reads too, so the same
  code tags mail in both tools:

  ```python
  EmailMessage(..., headers={"X-Tags": "billing, onboarding"})
  ```

- A function named by [`MAIL_PREVIEW_TAGS`](settings.md#mail_preview_tags), called
  with the `EmailMessage` as it's captured, for rules such as "everything from
  billing is `billing`":

  ```python
  MAIL_PREVIEW_TAGS = "myproject.mail.tags"
  ```

  ```python
  def tags(message):
      if message.from_email.startswith("billing@"):
          return ["billing"]
      return []
  ```

  It returns the tags as a list, or a comma-separated string like the header, or
  `None` for none. An error in it propagates, like any error while capturing.

- With [`MAIL_PREVIEW_PLUS_ADDRESSING`](settings.md#mail_preview_plus_addressing) set
  to `True`, the part after `+` in a recipient's address: a message to
  `ada+welcome@example.com` is tagged `welcome`. It's off by default, because a
  project that uses plus addressing for its own ends would get a tag per address.

Tags are fixed when the message is captured and normalised then: lowercased, trimmed,
spaces inside a tag turned into hyphens so `tag:` can always name one, duplicates
dropped, and sorted. Previews get no tags; they're grouped by app already.

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
Inbox heading in the sidebar shows the directory in a tooltip. Set
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
`MessageMeta.from_json()` serialise the metadata; `from_json()` reads a record written
before tags existed as untagged. See the [API reference](api.md#storage).

The system check `django_mail_preview.E002` reports a path that doesn't import or
doesn't name a concrete `BaseStorage` subclass.
