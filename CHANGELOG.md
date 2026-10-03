# Changelog

## Unreleased

## 0.2.0 (2026-10-03)

- The name at the top of the sidebar is now `mail.preview`, in monospace with the dot in the accent colour, beside an outlined tile; the page titles say the same. The favicon keeps the filled tile.
- The inbox table says how long ago a message arrived, "just now", "4 minutes ago", "2 days ago", instead of the date and time. The exact time is in a tooltip, and the wording keeps up while the page is open. The sidebar and the message page are unchanged.
- Tags on captured mail. They come from the message's `X-Tags` header, comma separated as Mailpit reads it, from a function named by the new `MAIL_PREVIEW_TAGS` setting, and, with `MAIL_PREVIEW_PLUS_ADDRESSING`, from the part after `+` in a recipient's address. They show as chips after the subject in the table, on the sidebar rows and on the message page, a row under the Inbox heading lists them with counts, a click on a chip filters the table, and `tag:` is a search operator. `MessageMeta` gains a `tags` field, and the checks `django_mail_preview.E005` and `E006` report the two settings when they can't be used.
- A search box beside the Inbox heading filters the table as you type. A word matches the subject and the addresses, `from:`, `to:` and `subject:` narrow it to one field, `has:attachment` keeps messages with attachments, and a leading `-` excludes. `/` focuses the box from any page, Escape clears it, and the query stays in the URL.
- A sun or moon button beside the name switches the pages between light and dark. The choice is kept in the browser and applied before the page paints; the email in the frame keeps the system's scheme.
- The sidebar's storage footer is gone. The Inbox heading shows the directory, or the storage class, in a tooltip.
- The start page without captured mail is an empty-inbox screen with one copyable command: the setting that points the project at the capture backend, or, once that is active, a `manage.py shell` one-liner that sends a message. A project without previews gets a link to the previews guide instead of a code sample.
- The version number no longer appears beside the name in the sidebar and the top bar.
- The frame's width presets are down to three: 375 px, 600 px and full width. The 320 and 768 px buttons are gone; the number field still takes any width.

## 0.1.0 (2026-10-03)

First release.

- A capture email backend, `django_mail_preview.backends.EmailBackend`, that stores every message sent through it instead of delivering it. It takes the place of `EMAIL_BACKEND` on Django 5.2 and 6.0 and of a `MAILERS` backend on Django 6.1, where it also records the alias a message went through.
- Captured messages are stored as files, one `.eml` with a JSON sidecar, under `MAIL_PREVIEW_ROOT`, which defaults to a per-project directory under the system temp dir. The newest `MAIL_PREVIEW_MAX_MESSAGES` are kept, 100 by default. Writes are atomic, and parallel sends from several threads or processes can't lose each other's mail. `MAIL_PREVIEW_STORAGE` swaps in a `BaseStorage` subclass of your own.
- Preview classes: subclass `django_mail_preview.EmailPreview` in an app's `previews.py`, and every public method that returns an `EmailMessage` is a preview, grouped by app in the sidebar. Previews are discovered when the page loads, a `previews.py` created while the server runs included, and are never imported in production. `self.params` carries the URL's query string into a preview, the first paragraph of the docstring is its description, and `get_previews()` lists them for a test that renders every one.
- The inbox pages, included with `path("__mail-preview__/", include("django_mail_preview.urls"))`: a sidebar with the previews by group and the captured mail newest first, a start page with the captured mail as a table, and a message page with the HTML in a sandboxed frame, the plain text, the source, the headers, the MIME tree and a parts list with downloads. The frame has width presets from 320 px to full width and a field for any width. Newer and Older buttons and the `j` and `k` keys move through captured mail, Copy buttons sit on the text and source tabs, and a message downloads as an `.eml` that opens in a mail client.
- The list refreshes itself while the page is open: the start page reloads when mail arrives, and a message page shows a badge, with the count of new messages in the tab's title and on the favicon.
- The pages answer 404 unless `DEBUG` is `True`; `MAIL_PREVIEW_ALLOW` names a function that decides instead. Email HTML renders in a sandboxed frame under a Content Security Policy that never runs a script, inline images arrive as `data:` URIs so a cookie-based gate still works, and parts and `.eml` files download under headers that keep an attachment from rendering in the site's origin. Django 6.0's CSP middleware leaves these responses alone.
- The pages work without `django.contrib.staticfiles` and without the project's `TEMPLATES`: the package serves its own stylesheet and script and renders its templates through its own engine. Phones get the sidebar as a drawer, and the colours follow the system's light or dark scheme.
- System checks: `django_mail_preview.E001` to `E004` report a `MAIL_PREVIEW_ALLOW`, `MAIL_PREVIEW_STORAGE`, `MAIL_PREVIEW_MAX_MESSAGES` or `MAIL_PREVIEW_ROOT` the package can't use, `W001` warns when the capture backend is active while `DEBUG` is `False`, `W002` reports an unknown `MAIL_PREVIEW_*` setting, and `W003` reports the backend active without the URLs included.
- Documentation with a quickstart, guides to the inbox and to previews, the settings, a security page and the limits.
