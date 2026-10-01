from __future__ import annotations

from django.urls import include, path

urlpatterns = [path("__mail-preview__/", include("django_mail_preview.urls"))]
