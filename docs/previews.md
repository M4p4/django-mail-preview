# Previews

A preview builds an email from sample data and shows it without sending it. Previews
live in a `previews.py` in any installed app and appear in the sidebar, grouped by
app.

## Writing previews

Subclass `EmailPreview`. Every public method is one preview. It takes no arguments and
returns an `EmailMessage`, or a subclass such as `EmailMultiAlternatives`, usually by
calling the function your app uses to build the real email:

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

Nothing registers the class, since subclassing is enough. The page imports `previews`
from every installed app when it loads, so a `previews.py` you create while
`runserver` is running appears on the next refresh, and the autoreloader watches it
from then on. Previews are never imported in production, because nothing imports them
until someone opens the pages.

A preview is rebuilt on every request to its page, its frame and its downloads, and
nothing about it is stored.

The first paragraph of a method's docstring shows under the preview's header, which
is a good place to say when the email is sent.

Methods whose name starts with an underscore are helpers, not previews. Static
methods, properties and nested classes aren't previews either.

A method that returns anything but an `EmailMessage` raises `TypeError` naming the
class and the method when the preview opens. Any other error in a preview propagates,
so Django's debug page points at the preview's own code.

## Sample data

Build sample objects without saving them. `User(first_name="Ada")` is enough for a
template that reads `user.first_name`, and it touches no database. When the email
needs a primary key, for `reverse("profile", args=[user.pk])` say, set one by hand:
`User(pk=1, first_name="Ada")`.

Avoid saving in a preview. It runs on every request, so each page load would add
rows. When an email needs rows, a fixture with known ids and a query in the preview
is the better shape.

## Grouping and names

The sidebar groups previews by the label of the app that contains the `previews.py`.
Several classes in one app merge into one group. The `group` attribute overrides the
label:

```python
class SupportEmails(EmailPreview):
    group = "shop"

    def ticket_reply(self): ...
```

A preview's id is `<group>.<method>`. It shows on the preview's page and in the
sidebar link's tooltip, and it makes the URL: `previews/<group>/<method>/`. Two
previews with the same id, that is two classes with the same group and method name,
raise `ImproperlyConfigured` naming both classes. Give one of them a different `group`
or rename the method.

`group`, `params`, `render` and `request` are attributes of the base class, so a
preview method can't have one of those names. `ImproperlyConfigured` says so.

## Parameters

Inside a method, `self.request` is the current request, or `None` outside a view, and
`self.params` is the request's query string as a `QueryDict`. Append `?items=3` to a
preview's URL to build a variant:

```python
class OrderEmails(EmailPreview):
    def receipt(self):
        """Takes ?items= for the number of items in the sample order, one unless given."""
        count = int(self.params.get("items", 1))
        return receipt_email(sample_order(items=count))
```

The query string reaches the frame and the downloads too, so the HTML tab and the
`.eml` show the same variant. The `tab` parameter is the page's own.

## Testing every preview

Previews are code, and they break when the email functions change. One parametrised
test renders every preview:

```python
import pytest

from django_mail_preview import get_previews


@pytest.mark.parametrize("preview", get_previews(), ids=lambda preview: preview.id)
def test_preview_renders(preview):
    preview.render()
```

`get_previews()` returns every preview sorted by id, and `render()` builds the message
without a request, so `params` is empty. With Django's test runner:

```python
from django.test import SimpleTestCase

from django_mail_preview import get_previews


class PreviewTests(SimpleTestCase):
    def test_every_preview_renders(self):
        for preview in get_previews():
            with self.subTest(preview=preview.id):
                preview.render()
```

Use `TestCase` instead when a preview reads the database.
