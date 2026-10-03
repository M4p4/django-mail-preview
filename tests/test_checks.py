from __future__ import annotations

from pathlib import Path

import django
import pytest
from django.core.checks import Error, Warning, run_checks
from django.test import override_settings

from django_mail_preview.checks import BACKEND, backend_is_active
from django_mail_preview.storage import FileStorage

SMTP = "django.core.mail.backends.smtp.EmailBackend"
CONSOLE = "django.core.mail.backends.console.EmailBackend"

# Django 6.1 deprecates EMAIL_BACKEND, and reading it warns under -W error.
email_backend_route = pytest.mark.skipif(
    django.VERSION >= (6, 1), reason="EMAIL_BACKEND is deprecated on Django 6.1"
)

INACTIVE = [
    {},
    {"MAILERS": {"default": {"BACKEND": SMTP}}},
    {"MAILERS": {"default": {}}},
    pytest.param({"EMAIL_BACKEND": CONSOLE}, marks=email_backend_route),
]

ACTIVE = [
    {"MAILERS": {"default": {"BACKEND": BACKEND}}},
    {"MAILERS": {"default": {"BACKEND": SMTP}, "dev": {"BACKEND": BACKEND}}},
    pytest.param({"EMAIL_BACKEND": BACKEND}, marks=email_backend_route),
]

NOT_CALLABLE = "staff"

urlpatterns: list[object] = []
"""A URLconf without the inbox, for the W003 tests."""


def allow_all(request):
    """A callable at a dotted path; the check only imports it."""


def tag_all(message):
    """A callable at a dotted path; the check only imports it."""


def test_no_messages_by_default():
    result = run_checks()

    assert result == []


@pytest.mark.parametrize("config", INACTIVE)
def test_backend_inactive(config):
    with override_settings(**config):
        active = backend_is_active()

    assert active is False


@pytest.mark.parametrize("config", ACTIVE)
def test_backend_active(config):
    with override_settings(**config):
        active = backend_is_active()

    assert active is True


@pytest.mark.parametrize("allow", [None, "tests.test_checks.allow_all"])
def test_allow_valid(allow):
    with override_settings(MAIL_PREVIEW_ALLOW=allow):
        result = run_checks()

    assert result == []


@pytest.mark.parametrize(
    "allow",
    [
        "tests.test_checks.missing",
        "missing.module.allow",
        "allow",
        "tests.test_checks.NOT_CALLABLE",
        allow_all,
    ],
)
def test_allow_invalid(allow):
    with override_settings(MAIL_PREVIEW_ALLOW=allow):
        result = run_checks()

    assert [message.id for message in result] == ["django_mail_preview.E001"]
    assert isinstance(result[0], Error)


@pytest.mark.parametrize(
    "storage",
    [
        "files",
        "django_mail_preview.storage.FileStorage",
        "tests.test_storage.MemoryStorage",
    ],
)
def test_storage_valid(storage):
    with override_settings(MAIL_PREVIEW_STORAGE=storage):
        result = run_checks()

    assert result == []


@pytest.mark.parametrize(
    ("storage", "problem"),
    [
        (None, "None is not a dotted path"),
        (FileStorage, "is not a dotted path"),
        ("missing.module.Storage", "missing"),
        ("tests.test_storage.missing", "missing"),
        ("FileStorage", "doesn't look like a module path"),
        ("tests.test_storage.NotAStorage", "is not a BaseStorage subclass"),
        ("tests.test_storage.meta", "is not a BaseStorage subclass"),
        ("django_mail_preview.storage.BaseStorage", "is abstract"),
    ],
)
def test_storage_invalid(storage, problem):
    with override_settings(MAIL_PREVIEW_STORAGE=storage):
        result = run_checks()

    assert [message.id for message in result] == ["django_mail_preview.E002"]
    assert isinstance(result[0], Error)
    assert problem in result[0].msg


@pytest.mark.parametrize("value", [1, 100])
def test_max_messages_valid(value):
    with override_settings(MAIL_PREVIEW_MAX_MESSAGES=value):
        result = run_checks()

    assert result == []


@pytest.mark.parametrize("value", [0, -1, True, False, 1.5, "100", None])
def test_max_messages_invalid(value):
    with override_settings(MAIL_PREVIEW_MAX_MESSAGES=value):
        result = run_checks()

    assert [message.id for message in result] == ["django_mail_preview.E003"]
    assert isinstance(result[0], Error)
    assert repr(value) in result[0].msg


@pytest.mark.parametrize(
    "root", ["/var/tmp/mail-preview", Path("/var/tmp/mail-preview")]
)
def test_root_valid(root):
    with override_settings(MAIL_PREVIEW_ROOT=root):
        result = run_checks()

    assert result == []


@pytest.mark.parametrize("root", [None, 1, b"/var/tmp/mail-preview", ["/var/tmp"]])
def test_root_invalid(root):
    with override_settings(MAIL_PREVIEW_ROOT=root):
        result = run_checks()

    assert [message.id for message in result] == ["django_mail_preview.E004"]
    assert isinstance(result[0], Error)


@pytest.mark.parametrize("tags", [None, "tests.test_checks.tag_all"])
def test_tags_valid(tags):
    with override_settings(MAIL_PREVIEW_TAGS=tags):
        result = run_checks()

    assert result == []


@pytest.mark.parametrize(
    "tags",
    [
        "tests.test_checks.missing",
        "missing.module.tags",
        "tags",
        "tests.test_checks.NOT_CALLABLE",
        tag_all,
    ],
)
def test_tags_invalid(tags):
    with override_settings(MAIL_PREVIEW_TAGS=tags):
        result = run_checks()

    assert [message.id for message in result] == ["django_mail_preview.E005"]
    assert isinstance(result[0], Error)


@pytest.mark.parametrize("value", [True, False])
def test_plus_addressing_valid(value):
    with override_settings(MAIL_PREVIEW_PLUS_ADDRESSING=value):
        result = run_checks()

    assert result == []


@pytest.mark.parametrize("value", [1, 0, "yes", None])
def test_plus_addressing_invalid(value):
    with override_settings(MAIL_PREVIEW_PLUS_ADDRESSING=value):
        result = run_checks()

    assert [message.id for message in result] == ["django_mail_preview.E006"]
    assert isinstance(result[0], Error)
    assert repr(value) in result[0].msg


@pytest.mark.parametrize("config", ACTIVE)
def test_backend_without_debug_warns(config):
    with override_settings(DEBUG=False, **config):
        result = run_checks()

    assert [message.id for message in result] == ["django_mail_preview.W001"]
    assert isinstance(result[0], Warning)
    assert "captured, not delivered" in result[0].msg


@pytest.mark.parametrize("config", ACTIVE)
def test_backend_with_debug_is_fine(config):
    with override_settings(DEBUG=True, **config):
        result = run_checks()

    assert result == []


@pytest.mark.parametrize("config", INACTIVE)
def test_debug_off_without_backend_is_fine(config):
    with override_settings(DEBUG=False, **config):
        result = run_checks()

    assert result == []


@pytest.mark.parametrize(
    ("name", "hint"),
    [
        ("MAIL_PREVIEW_MAX_MESSAGE", "Did you mean MAIL_PREVIEW_MAX_MESSAGES?"),
        ("MAIL_PREVIEW_ALLOWED", "Did you mean MAIL_PREVIEW_ALLOW?"),
        ("MAIL_PREVIEW_POLL_INTERVAL", "Remove it."),
    ],
)
def test_unknown_setting_warns(name, hint):
    with override_settings(**{name: 1}):
        result = run_checks()

    assert [message.id for message in result] == ["django_mail_preview.W002"]
    assert isinstance(result[0], Warning)
    assert name in result[0].msg
    assert result[0].hint == hint


@pytest.mark.parametrize("config", ACTIVE)
def test_backend_without_urls_warns(config):
    with override_settings(ROOT_URLCONF="tests.test_checks", **config):
        result = run_checks()

    assert [message.id for message in result] == ["django_mail_preview.W003"]
    assert isinstance(result[0], Warning)
    assert (
        result[0].hint
        == "Add path('__mail-preview__/', include('django_mail_preview.urls')) to the project's urlpatterns."
    )


@pytest.mark.parametrize("config", ACTIVE)
def test_backend_with_urls_is_fine(config):
    with override_settings(ROOT_URLCONF="tests.urls", **config):
        result = run_checks()

    assert result == []


@pytest.mark.parametrize("config", INACTIVE)
def test_no_urls_without_backend_is_fine(config):
    with override_settings(ROOT_URLCONF="tests.test_checks", **config):
        result = run_checks()

    assert result == []


@pytest.mark.parametrize("config", ACTIVE)
def test_no_urlconf_is_fine(config):
    """A script set up with settings.configure() has no pages to include."""
    with override_settings(ROOT_URLCONF=None, **config):
        result = run_checks()

    assert result == []
