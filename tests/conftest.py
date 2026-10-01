from __future__ import annotations

import django.test
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


@pytest.fixture
def client():
    """A test client that closes every response it got once the test is over.

    The client only closes a streaming response once its content was read, so
    an unread ``FileResponse`` would leak its open file and raise a
    ``ResourceWarning`` under ``PYTHONDEVMODE``.
    """
    responses = []

    class Client(django.test.Client):
        def request(self, **request):
            response = super().request(**request)
            responses.append(response)
            return response

    yield Client()
    for response in responses:
        response.close()
