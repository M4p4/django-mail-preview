from __future__ import annotations

SECRET_KEY = "django-mail-preview-tests"

DEBUG = True

DATABASES: dict[str, dict[str, object]] = {}

TEMPLATES: list[dict[str, object]] = []

INSTALLED_APPS = ["django_mail_preview", "tests"]

ROOT_URLCONF = "tests.urls"

MIDDLEWARE = [
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

CACHES = {
    "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"},
}
