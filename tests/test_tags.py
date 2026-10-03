from __future__ import annotations

import pytest
from django.core.mail import EmailMessage
from django.test import override_settings

from django_mail_preview.tags import normalise, tags_for


def message(**kwargs):
    defaults = {
        "subject": "Hello",
        "body": "Hi there.",
        "from_email": "sender@example.com",
        "to": ["to@example.com"],
    }
    return EmailMessage(**{**defaults, **kwargs})


def by_sender(message):
    """A hook: everything from billing is ``billing``."""
    return ["billing"] if message.from_email.startswith("billing@") else []


def as_string(message):
    return "Billing, onboarding"


def as_generator(message):
    yield "a"
    yield 2


def nothing(message):
    return None


def not_iterable(message):
    return 7


def broken(message):
    raise RuntimeError("boom")


def hook(name):
    return override_settings(MAIL_PREVIEW_TAGS=f"tests.test_tags.{name}")


def plus():
    return override_settings(MAIL_PREVIEW_PLUS_ADDRESSING=True)


@pytest.mark.parametrize(
    ("tags", "expected"),
    [
        ([], ()),
        (["Billing"], ("billing",)),
        ([" billing ", "billing", "BILLING"], ("billing",)),
        (["onboarding", "billing"], ("billing", "onboarding")),
        (["", "  ", "\t"], ()),
        (["new  user", " Q4 \n report "], ("new-user", "q4-report")),
    ],
)
def test_normalise(tags, expected):
    assert normalise(tags) == expected


def test_no_source_means_no_tags():
    assert tags_for(message()) == ()


@pytest.mark.parametrize("name", ["X-Tags", "x-tags", "X-TAGS"])
def test_header(name):
    """The header by any case of its name, among the message's other headers."""
    headers = {"X-Priority": "1", name: "Onboarding, billing ,, "}

    tags = tags_for(message(headers=headers))

    assert tags == ("billing", "onboarding")


def test_hook_sees_the_message():
    with hook("by_sender"):
        billing = tags_for(message(from_email="billing@example.com"))
        other = tags_for(message())

    assert billing == ("billing",)
    assert other == ()


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("as_string", ("billing", "onboarding")),
        ("as_generator", ("2", "a")),
        ("nothing", ()),
    ],
)
def test_hook_result_forms(name, expected):
    with hook(name):
        tags = tags_for(message())

    assert tags == expected


def test_hook_error_propagates():
    with hook("broken"), pytest.raises(RuntimeError, match="boom"):
        tags_for(message())


def test_hook_result_must_be_iterable():
    with hook("not_iterable"), pytest.raises(TypeError, match="returned 7"):
        tags_for(message())


@pytest.mark.parametrize(
    ("recipient", "expected"),
    [
        ("ada+welcome@example.com", ("welcome",)),
        ('"Ada Lovelace" <ada+Welcome@example.com>', ("welcome",)),
        ("ada+a+b@example.com", ("a+b",)),
        ("ada+@example.com", ()),
        ("ada@example.com", ()),
    ],
)
def test_plus_addressing(recipient, expected):
    with plus():
        tags = tags_for(message(to=[recipient]))

    assert tags == expected


def test_plus_addressing_reads_every_recipient():
    with plus():
        tags = tags_for(
            message(
                to=["ada+to@example.com"],
                cc=["grace+cc@example.com"],
                bcc=["linus+bcc@example.com"],
                reply_to=["ops+reply@example.com"],
            )
        )

    assert tags == ("bcc", "cc", "to")


def test_plus_addressing_is_off_by_default():
    assert tags_for(message(to=["ada+welcome@example.com"])) == ()


def test_sources_merge():
    with hook("by_sender"), plus():
        tags = tags_for(
            message(
                from_email="billing@example.com",
                to=["ada+welcome@example.com"],
                headers={"X-Tags": "Billing, invoice"},
            )
        )

    assert tags == ("billing", "invoice", "welcome")
