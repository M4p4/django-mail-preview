# Installation

django-mail-preview supports Python 3.10 or newer and Django 5.2, 6.0 and 6.1. Django
is its only dependency, and it adds no models, migrations or management commands.

Install the package:

```console
$ pip install django-mail-preview
```

Add the app to `INSTALLED_APPS`:

```python
INSTALLED_APPS = [
    # ...
    "django_mail_preview",
]
```

## The capture backend

Point Django's mail at the capture backend. On Django 6.1 and later, name it in
`MAILERS`:

```python
MAILERS = {
    "default": {"BACKEND": "django_mail_preview.backends.EmailBackend"},
}
```

On Django 5.2 and 6.0, set `EMAIL_BACKEND`:

```python
EMAIL_BACKEND = "django_mail_preview.backends.EmailBackend"
```

Django 6.1 still reads `EMAIL_BACKEND` but warns that it's deprecated, and Django 7.0
removes it, so switch to `MAILERS` when you upgrade.

The backend takes no `OPTIONS`. Everything it needs comes from the
[settings](settings.md), so the backend and the pages read the same configuration.

Use the backend in your development settings only. It stores mail instead of
delivering it, and the system check `django_mail_preview.W001` warns when it's active
while `DEBUG` is `False`.

## The URLs

Include the URLs under any prefix. `__mail-preview__/` keeps them out of the way of
your own routes:

```python
from django.urls import include, path

urlpatterns = [
    # ...
    path("__mail-preview__/", include("django_mail_preview.urls")),
]
```

The include can stay in `urlpatterns` unconditionally. Every view answers 404 unless
`DEBUG` is `True`, or unless [`MAIL_PREVIEW_ALLOW`](settings.md#mail_preview_allow)
says otherwise, so the pages don't exist for anyone else. When the capture backend is
active without the include, the system check `django_mail_preview.W003` reminds you.

The pages need neither `django.contrib.staticfiles` nor your project's `TEMPLATES`.
They serve their own stylesheet and script and render through their own template
engine, so a Jinja2-only or API-only project works too.

## First load

Open `http://localhost:8000/__mail-preview__/`. Before anything is sent, the page says
what to do next: it shows the settings to add when the capture backend isn't active,
and an example `previews.py` when no app has one. Send a message from a shell to see
the first one arrive:

```console
$ python manage.py shell
>>> from django.core.mail import send_mail
>>> send_mail("Hello", "The first captured message.", "noreply@example.com", ["ada@example.com"])
1
```

The page notices new mail within a few seconds and lists the message. The
[Inbox](inbox.md) page describes what you see.

## Docker and several processes

Captured messages are files. By default they live in a directory under the system temp
dir, named after a hash of your `BASE_DIR`, so two projects on one machine don't share
an inbox. The sidebar's footer shows the directory in use.

Containers don't share `/tmp`. When the web server and a worker run in separate
containers, mail the worker sends lands in the worker's temp dir, where the web
container's pages can't see it. Set `MAIL_PREVIEW_ROOT` to a directory on a volume
both containers mount:

```python
MAIL_PREVIEW_ROOT = "/data/mail-preview"
```

The same goes for any two processes whose temp dirs differ.
