"""Sample previews, discovered through the ``tests`` app."""

from __future__ import annotations

from django.core.mail import EmailMessage, EmailMultiAlternatives

from django_mail_preview import EmailPreview
from tests.helpers import inline_image

GREETINGS = {"en": "Hello Ada", "de": "Hallo Ada"}


class Samples(EmailPreview):
    def plain(self):
        return EmailMessage(
            "Welcome", "Hello Ada.", "noreply@example.com", ["ada@example.com"]
        )

    def html(self):
        """A welcome with an inline logo and an attachment."""
        message = EmailMultiAlternatives(
            "Welcome", "Hello Ada.", "noreply@example.com", ["ada@example.com"]
        )
        message.attach_alternative(
            '<p>Hello Ada.</p><img src="cid:logo" alt="">', "text/html"
        )
        message.attach(inline_image("logo"))
        message.attach("terms.txt", b"The terms.", "text/plain")
        return message

    def greeting(self):
        """Greets in the language of ``?lang=``,
        English unless given.

        Shows how a preview reads the query string.
        """
        language = self.params.get("lang", "en")
        return EmailMessage(
            GREETINGS[language], "Welcome!", "noreply@example.com", ["ada@example.com"]
        )
