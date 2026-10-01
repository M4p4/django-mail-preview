from __future__ import annotations

SECRET_KEY = "django-mail-preview-tests"

DEBUG = True

DATABASES = {}

TEMPLATES = []

INSTALLED_APPS = ["django_mail_preview", "tests"]

ROOT_URLCONF = "tests.urls"

MIDDLEWARE = [
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

CACHES = {
    "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"},
}
