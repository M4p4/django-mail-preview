from __future__ import annotations

import hashlib
import tempfile
from pathlib import Path

import pytest
from django.apps import apps
from django.conf import settings as django_settings
from django.test import override_settings

from django_mail_preview.apps import DjangoMailPreviewConfig
from django_mail_preview.conf import default_root, mail_preview_settings

DEFAULTS = [
    ("STORAGE", "files"),
    ("MAX_MESSAGES", 100),
    ("ALLOW", None),
    ("TAGS", None),
    ("PLUS_ADDRESSING", False),
]

OVERRIDES = [
    ("STORAGE", "myproject.mail.CacheStorage"),
    ("ROOT", "/var/tmp/mail-preview"),
    ("MAX_MESSAGES", 10),
    ("ALLOW", "myproject.utils.mail_preview_allowed"),
    ("TAGS", "myproject.mail.tags"),
    ("PLUS_ADDRESSING", True),
]

TEMP_ROOT = Path(tempfile.gettempdir()) / "django-mail-preview"


def test_every_setting_is_tested():
    names = {name for name in vars(type(mail_preview_settings)) if name.isupper()}

    assert names == {name for name, _ in DEFAULTS} | {"ROOT"}
    assert names == {name for name, _ in OVERRIDES}


@pytest.mark.parametrize(("name", "expected"), DEFAULTS)
def test_default(name, expected):
    value = getattr(mail_preview_settings, name)

    assert value == expected


def test_root_default(settings):
    del settings.MAIL_PREVIEW_ROOT

    value = mail_preview_settings.ROOT

    assert value == default_root()


@pytest.mark.parametrize(("name", "value"), OVERRIDES)
def test_override(name, value):
    with override_settings(**{f"MAIL_PREVIEW_{name}": value}):
        result = getattr(mail_preview_settings, name)

    assert result == value


@pytest.mark.parametrize("convert", [Path, str])
def test_default_root_from_base_dir(convert, tmp_path):
    with override_settings(BASE_DIR=convert(tmp_path)):
        root = default_root()

    key = hashlib.sha256(str(tmp_path).encode()).hexdigest()[:12]
    assert root == TEMP_ROOT / key


def test_default_root_from_settings_module():
    assert not hasattr(django_settings, "BASE_DIR")

    with override_settings(SETTINGS_MODULE="myproject.settings"):
        root = default_root()

    key = hashlib.sha256(b"myproject.settings").hexdigest()[:12]
    assert root == TEMP_ROOT / key


def test_default_root_differs_per_project(tmp_path):
    with override_settings(BASE_DIR=tmp_path / "one"):
        one = default_root()
    with override_settings(BASE_DIR=tmp_path / "two"):
        two = default_root()

    assert one != two
    assert one.parent == two.parent == TEMP_ROOT


def test_app_config():
    config = apps.get_app_config("django_mail_preview")

    assert isinstance(config, DjangoMailPreviewConfig)
    assert config.verbose_name == "Mail preview"
