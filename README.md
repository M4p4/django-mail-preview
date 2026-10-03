# django-mail-preview

[![PyPI version](https://img.shields.io/pypi/v/django-mail-preview.svg)](https://pypi.org/project/django-mail-preview/)
[![Python versions](https://img.shields.io/pypi/pyversions/django-mail-preview.svg)](https://pypi.org/project/django-mail-preview/)
[![CI](https://github.com/M4p4/django-mail-preview/actions/workflows/main.yml/badge.svg)](https://github.com/M4p4/django-mail-preview/actions/workflows/main.yml)
[![Documentation](https://readthedocs.org/projects/django-mail-preview/badge/?version=stable)](https://django-mail-preview.readthedocs.io/)

See every email your Django app sends, rendered in the browser, without sending a
single one.

Checking email in a Django project usually means reading raw MIME in the console or
sending real mail to a test inbox. django-mail-preview gives you one page inside the
project instead: a capture email backend stores the mail your app sends, and preview
classes build emails from sample data without sending them. The page answers 404
unless `DEBUG` is on, needs no `staticfiles`, and adds no models or migrations. Django
is the only dependency.

![A captured message rendered in a sandboxed frame at 600 px wide, with the previews grouped by app in the sidebar](https://raw.githubusercontent.com/M4p4/django-mail-preview/main/docs/_static/inbox.png)

## Quickstart

```console
python -m pip install django-mail-preview
```

Add the app and the capture backend to your settings:

```python
INSTALLED_APPS = [
    # ...
    "django_mail_preview",
]

# Django 6.1 and later
MAILERS = {
    "default": {"BACKEND": "django_mail_preview.backends.EmailBackend"},
}

# Django 5.2 and 6.0
EMAIL_BACKEND = "django_mail_preview.backends.EmailBackend"
```

Include the URLs:

```python
from django.urls import include, path

urlpatterns = [
    # ...
    path("__mail-preview__/", include("django_mail_preview.urls")),
]
```

Open <http://localhost:8000/__mail-preview__/>. Every email the app sends from now on
appears there, rendered in a sandboxed frame, with its plain text, source, headers and
attachments a tab away. The include needs no `if settings.DEBUG` wrapper, because the
views answer 404 unless `DEBUG` is on.

## Previews

To see an email without triggering it, add a `previews.py` to any app. Each public
method of an `EmailPreview` subclass builds one email from sample data:

```python
# accounts/previews.py
from django_mail_preview import EmailPreview

from .emails import password_reset_email, welcome_email
from .models import User


class AccountEmails(EmailPreview):
    def password_reset(self):
        """Sent after the "forgot password" form."""
        user = User(first_name="Ada", email="ada@example.com")
        return password_reset_email(user)

    def welcome(self):
        return welcome_email(User(first_name="Ada"))
```

Refresh the page, and the sidebar lists `password_reset` and `welcome` under
`accounts`. Previews are found by convention, rebuilt on every request and never
imported in production. A query string on a preview's URL reaches it as
`self.params`, so one method can show variants. One parametrised test renders every
preview:

```python
import pytest

from django_mail_preview import get_previews


@pytest.mark.parametrize("preview", get_previews(), ids=lambda preview: preview.id)
def test_preview_renders(preview):
    preview.render()
```

## Compatibility

| Python | Django |
|---|---|
| 3.10, 3.11 | 5.2 |
| 3.12, 3.13, 3.14 | 5.2, 6.0, 6.1 |

## Security

The pages answer 404 unless `DEBUG` is `True`, and `MAIL_PREVIEW_ALLOW` replaces that
rule with your own check for a staging server. Email HTML renders in a sandboxed frame
under a Content Security Policy that lets images and styles load but never runs a
script, and every attachment downloads instead of rendering in your site's origin.

## Documentation

The full documentation is at
[django-mail-preview.readthedocs.io](https://django-mail-preview.readthedocs.io/):

- [Installation](https://django-mail-preview.readthedocs.io/en/stable/installation.html)
- [Inbox](https://django-mail-preview.readthedocs.io/en/stable/inbox.html)
- [Previews](https://django-mail-preview.readthedocs.io/en/stable/previews.html)
- [Settings](https://django-mail-preview.readthedocs.io/en/stable/settings.html)
- [Security](https://django-mail-preview.readthedocs.io/en/stable/security.html)
- [Limits](https://django-mail-preview.readthedocs.io/en/stable/limits.html)
- [Contributing](https://django-mail-preview.readthedocs.io/en/stable/contributing.html)

## License

MIT.
