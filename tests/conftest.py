from __future__ import annotations

import pytest

from django_mail_preview.registry import autodiscover, registry


@pytest.fixture(autouse=True)
def mail_preview_root(settings, tmp_path):
    settings.MAIL_PREVIEW_ROOT = tmp_path
    return tmp_path


@pytest.fixture(autouse=True)
def preview_registry():
    """Previews defined inside a test don't leak into the others.

    Autodiscovers first, so the sample previews are part of the snapshot
    whichever test imports them first.
    """
    autodiscover()
    snapshot = dict(registry)
    yield registry
    registry.clear()
    registry.update(snapshot)
