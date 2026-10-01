from __future__ import annotations

from django.apps import AppConfig
from django.core.checks import register

from django_mail_preview.checks import (
    check_allow,
    check_backend_without_debug,
    check_max_messages,
    check_root,
    check_storage,
    check_unknown_settings,
    check_urls,
)


class DjangoMailPreviewConfig(AppConfig):
    name = "django_mail_preview"
    verbose_name = "Mail preview"

    def ready(self) -> None:
        for check in (
            check_allow,
            check_storage,
            check_max_messages,
            check_root,
            check_backend_without_debug,
            check_unknown_settings,
            check_urls,
        ):
            register(check)
