# Limits

What django-mail-preview doesn't do, and why.

## Mail sent in tests isn't captured

Django's test runner replaces the email backend with the in-memory one for the whole
run, so your tests read `mail.outbox` as before and the inbox stays untouched. To
capture mail from a test on purpose, override `MAILERS` or `EMAIL_BACKEND` in that
test.

## Other connections and aliases aren't captured

Only mail sent through the capture backend is stored. A message sent with an explicit
connection, `get_connection("django.core.mail.backends.smtp.EmailBackend")` say, or
on Django 6.1 through a `MAILERS` alias that names another backend, goes where that
backend sends it. django-mail-preview is not an SMTP server, so mail from other
programs never appears either.

## The frame has a fixed height

A sandboxed frame has no origin, so it can't tell the page how tall its content is.
The frame takes most of the viewport and scrolls inside. "Open in new tab" shows the
HTML at its full height.

## Previews run in the request's language

A preview runs inside the request to its page, so Django's translations are in
whatever language that request activated, through `LocaleMiddleware` or
`LANGUAGE_CODE`. To preview an email in another language, activate it inside the
preview with `translation.override()`, driven by `self.params` if you like.

## The Source tab isn't the SMTP wire form

Source shows the message as Django serialised it, which is also what the `.eml`
contains: UTF-8 bodies with CRLF line endings. An SMTP server may receive a
transfer-encoded form of the same message, so the bytes on the wire can differ.

## No read state

The count in the tab's title and on the favicon is the number of messages that
arrived since the page loaded, not an unread count. Messages aren't marked read.

## No production use

The backend captures mail instead of delivering it. It belongs in development
settings, and the system check `django_mail_preview.W001` warns when it's active
while `DEBUG` is `False`.
