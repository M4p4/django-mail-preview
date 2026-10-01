from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def mail_preview_root(settings, tmp_path):
    settings.MAIL_PREVIEW_ROOT = tmp_path
    return tmp_path
