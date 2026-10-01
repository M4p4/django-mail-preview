from __future__ import annotations

import re
from base64 import b64encode
from unittest.mock import Mock

import django
import pytest
from django.core.mail import EmailMessage, EmailMultiAlternatives
from django.test import Client
from django.urls import reverse

from django_mail_preview import views
from django_mail_preview.backends import EmailBackend
from django_mail_preview.checks import BACKEND
from django_mail_preview.storage import FileStorage
from tests.helpers import PNG, inline_image

FRAME_CSP = (
    "default-src 'none'; img-src data: http: https:; "
    "style-src 'unsafe-inline' http: https:; font-src data: http: https:; "
    "base-uri 'none'; frame-ancestors 'self'; "
    "sandbox allow-popups allow-popups-to-escape-sandbox"
)
DOWNLOAD_CSP = "sandbox; default-src 'none'"
HTML = (
    '<html><head></head><body><p>Hi there.</p><img src="cid:logo" alt=""></body></html>'
)
SVG = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'
UNKNOWN_ID = "20261001-120000-123456-0badcafe"
KEY = "open-sesame"

csp_middleware = pytest.mark.skipif(
    django.VERSION < (6, 0), reason="Django 6.0 added the CSP middleware"
)

ROUTES = {
    "index": lambda id: route("index"),
    "sent_latest": lambda id: route("sent_latest"),
    "sent": lambda id: route("sent", id=id),
    "sent_html": lambda id: route("sent_html", id=id),
    "sent_part": lambda id: route("sent_part", id=id, n=0),
    "sent_eml": lambda id: route("sent_eml", id=id),
    "sent_delete": lambda id: route("sent_delete", id=id),
    "sent_clear": lambda id: route("sent_clear"),
    "asset": lambda id: route("asset", name="preview.css"),
}

BY_ID = [("sent", {}), ("sent_html", {}), ("sent_part", {"n": 0}), ("sent_eml", {})]


def allow_with_key(request):
    """A MAIL_PREVIEW_ALLOW callable: opens the pages to requests that know the key."""
    return request.headers.get("X-Key") == KEY


def route(view, **kwargs):
    return reverse(f"mail_preview:{view}", kwargs=kwargs or None)


def plain(subject="Hello"):
    return EmailMessage(subject, "Hi there.", "sender@example.com", ["to@example.com"])


def html(subject="Welcome"):
    """An HTML message with an inline image, an SVG attachment and every address header."""
    message = EmailMultiAlternatives(
        subject,
        "Hi there.",
        "sender@example.com",
        ["to@example.com"],
        cc=["cc@example.com"],
        bcc=["bcc@example.com"],
        reply_to=["reply@example.com"],
    )
    message.attach_alternative(HTML, "text/html")
    message.attach(inline_image("logo"))
    message.attach("report.svg", SVG, "image/svg+xml")
    return message


def capture(message):
    """Send one message through the capture backend and return its id."""
    EmailBackend().send_messages([message])
    return FileStorage().list()[0].meta.id


def current_tab(response):
    (tab,) = re.findall(
        r'data-tab="(\w+)" aria-current="page"', response.content.decode()
    )
    return tab


@pytest.mark.parametrize("page", ROUTES.values(), ids=list(ROUTES))
def test_pages_are_404_while_debug_is_off(settings, client, page):
    settings.DEBUG = False
    id = capture(html())

    response = client.get(page(id))

    assert response.status_code == 404


@pytest.mark.parametrize("debug", [True, False])
def test_allow_callable_replaces_the_debug_rule(settings, client, debug):
    settings.DEBUG = debug
    settings.MAIL_PREVIEW_ALLOW = "tests.test_views.allow_with_key"

    denied = client.get(route("index"))
    allowed = client.get(route("index"), headers={"X-Key": KEY})

    assert denied.status_code == 404
    assert allowed.status_code == 200


def test_index_lists_captured_mail_newest_first(client):
    first = capture(plain("First"))
    second = capture(plain("Second"))

    response = client.get(route("index"))

    content = response.content.decode()
    assert response.status_code == 200
    assert "Sent · 2" in content
    assert content.index(route("sent", id=second)) < content.index(
        route("sent", id=first)
    )
    assert 'name="csrfmiddlewaretoken"' in content
    assert f"files · {FileStorage().root}" in content


def test_index_hints_at_the_backend_until_it_is_active(settings, client):
    before = client.get(route("index"))
    settings.MAILERS = {"default": {"BACKEND": BACKEND}}
    after = client.get(route("index"))

    assert BACKEND in before.content.decode()
    assert BACKEND not in after.content.decode()


def test_footer_names_a_custom_storage(settings, client):
    settings.MAIL_PREVIEW_STORAGE = "tests.test_storage.MemoryStorage"

    response = client.get(route("index"))

    assert "tests.test_storage.MemoryStorage" in response.content.decode()


def test_message_page(client):
    id = capture(html())

    response = client.get(route("sent", id=id))

    content = response.content.decode()
    assert response.status_code == 200
    assert "<title>Welcome · Mail preview</title>" in content
    for address in ("sender", "to", "cc", "bcc", "reply"):
        assert f"{address}@example.com" in content
    assert f'<iframe src="{route("sent_html", id=id)}"' in content
    assert route("sent_eml", id=id) in content
    assert route("sent_delete", id=id) in content
    assert 'name="csrfmiddlewaretoken"' in content
    # The attachment and, under "Inline", the image without a filename.
    assert route("sent_part", id=id, n=1) in content
    assert "report.svg" in content
    assert "part-0" in content
    # The open message in the sidebar, and the current tab.
    assert content.count('aria-current="page"') == 2


def test_tabs_show_text_source_and_headers(client):
    id = capture(plain())

    response = client.get(route("sent", id=id))

    content = response.content.decode()
    assert "The message has no HTML part." in content
    assert "<pre>Hi there." in content
    assert "Subject: Hello" in content
    assert '<th scope="row">Message-ID</th>' in content


@pytest.mark.parametrize(
    ("build", "query", "tab"),
    [
        (html, "", "html"),
        (plain, "", "text"),
        (html, "?tab=text", "text"),
        (html, "?tab=source", "source"),
        (plain, "?tab=headers", "headers"),
        (html, "?tab=bogus", "html"),
    ],
)
def test_tab_selection(client, build, query, tab):
    id = capture(build())

    response = client.get(route("sent", id=id) + query)

    assert current_tab(response) == tab


def test_tab_links_keep_the_other_query_parameters(client):
    id = capture(plain())

    response = client.get(route("sent", id=id) + "?lang=de")

    assert 'href="?lang=de&amp;tab=source"' in response.content.decode()


def test_frame_serves_the_prepared_html_under_its_own_policy(client):
    id = capture(html())

    response = client.get(route("sent_html", id=id))

    content = response.content.decode()
    assert response.status_code == 200
    assert response["Content-Type"] == "text/html; charset=utf-8"
    assert response["Content-Security-Policy"] == FRAME_CSP
    assert response["X-Frame-Options"] == "SAMEORIGIN"
    assert response["Referrer-Policy"] == "no-referrer"
    assert content.startswith('<html><head><base target="_blank"></head>')
    assert f'<img src="data:image/png;base64,{b64encode(PNG).decode()}"' in content


def test_frame_embeds_inline_parts_so_it_makes_no_gated_request(settings, client):
    """The sandboxed frame has an opaque origin and sends no cookie, so a cookie-based gate would 404 its part requests."""
    settings.MAIL_PREVIEW_ALLOW = "tests.test_views.allow_with_key"
    id = capture(html())

    response = client.get(route("sent_html", id=id), headers={"X-Key": KEY})

    content = response.content.decode()
    assert response.status_code == 200
    assert "data:image/png;base64," in content
    assert route("sent_part", id=id, n=0) not in content


def test_frame_leaves_an_unknown_cid_alone(client):
    message = EmailMultiAlternatives(
        "Welcome", "Hi there.", "sender@example.com", ["to@example.com"]
    )
    message.attach_alternative('<img src="cid:missing" alt="">', "text/html")
    id = capture(message)

    response = client.get(route("sent_html", id=id))

    assert '<img src="cid:missing" alt="">' in response.content.decode()


def test_frame_of_a_message_without_html_is_404(client):
    id = capture(plain())

    response = client.get(route("sent_html", id=id))

    assert response.status_code == 404


@pytest.mark.parametrize(
    ("n", "content_type", "disposition", "body"),
    [
        (0, "image/png", 'attachment; filename="part-0"', PNG),
        (1, "image/svg+xml", 'attachment; filename="report.svg"', SVG),
    ],
)
def test_parts_download_whatever_their_type(client, n, content_type, disposition, body):
    id = capture(html())

    response = client.get(route("sent_part", id=id, n=n))

    assert response.status_code == 200
    assert response["Content-Type"] == content_type
    assert response["Content-Disposition"] == disposition
    assert response["X-Content-Type-Options"] == "nosniff"
    assert response["Content-Security-Policy"] == DOWNLOAD_CSP
    assert response.content == body


def test_part_beyond_the_last_is_404(client):
    id = capture(html())

    response = client.get(route("sent_part", id=id, n=2))

    assert response.status_code == 404


def test_eml_downloads_the_stored_bytes(client, mail_preview_root):
    id = capture(plain())

    response = client.get(route("sent_eml", id=id))

    assert response.status_code == 200
    assert response["Content-Type"] == "message/rfc822"
    assert response["Content-Disposition"] == f'attachment; filename="{id}.eml"'
    assert response["X-Content-Type-Options"] == "nosniff"
    assert response["Content-Security-Policy"] == DOWNLOAD_CSP
    assert response.content == (mail_preview_root / f"{id}.eml").read_bytes()
    assert b"\r\n" in response.content


@pytest.mark.parametrize(("name", "kwargs"), BY_ID)
def test_unknown_id_is_404(client, name, kwargs):
    response = client.get(route(name, id=UNKNOWN_ID, **kwargs))

    assert response.status_code == 404


@pytest.mark.parametrize(("name", "kwargs"), BY_ID)
def test_message_whose_bytes_vanished_is_404(client, mail_preview_root, name, kwargs):
    id = capture(html())
    (mail_preview_root / f"{id}.eml").unlink()

    response = client.get(route(name, id=id, **kwargs))

    assert response.status_code == 404


@pytest.mark.parametrize(
    "bad",
    [
        "not-an-id",
        "20261001-120000-123456-0BADCAFE",
        "20261001-120000-123456-0badcaf",
        "..",
        f"{UNKNOWN_ID}/..",
    ],
)
def test_malformed_id_never_reaches_the_storage(client, monkeypatch, bad):
    get_storage = Mock()
    monkeypatch.setattr(views, "get_storage", get_storage)

    response = client.get(f"{route('index')}sent/{bad}/")

    assert response.status_code == 404
    get_storage.assert_not_called()


def test_clear_route_is_not_taken_for_an_id(client):
    response = client.get(f"{route('index')}sent/clear/")

    assert response.status_code == 405


def test_delete_removes_the_message_and_returns_to_the_inbox(client):
    kept = capture(plain("Keep"))
    gone = capture(plain("Gone"))

    response = client.post(route("sent_delete", id=gone))

    assert response.status_code == 302
    assert response["Location"] == route("index")
    assert [stored.meta.id for stored in FileStorage().list()] == [kept]


def test_delete_of_an_unknown_id_is_silent(client):
    response = client.post(route("sent_delete", id=UNKNOWN_ID))

    assert response.status_code == 302


def test_clear_removes_every_message_and_returns_to_the_inbox(client):
    capture(plain("One"))
    capture(plain("Two"))

    response = client.post(route("sent_clear"))

    assert response.status_code == 302
    assert response["Location"] == route("index")
    assert FileStorage().list() == []


@pytest.mark.parametrize(
    ("name", "kwargs"), [("sent_delete", {"id": UNKNOWN_ID}), ("sent_clear", {})]
)
def test_post_views_refuse_get(client, name, kwargs):
    response = client.get(route(name, **kwargs))

    assert response.status_code == 405


@pytest.mark.parametrize(
    ("name", "kwargs"), [("sent_delete", {"id": UNKNOWN_ID}), ("sent_clear", {})]
)
def test_post_without_the_csrf_token_is_403(name, kwargs):
    client = Client(enforce_csrf_checks=True)

    response = client.post(route(name, **kwargs))

    assert response.status_code == 403


@pytest.mark.parametrize("project_middleware", [True, False])
@pytest.mark.parametrize(
    ("page", "action"), [("index", "sent_clear"), ("sent", "sent_delete")]
)
def test_forms_carry_a_token_that_passes(settings, project_middleware, page, action):
    """The pages set the cookie themselves, so the forms work without the project's CsrfViewMiddleware."""
    if not project_middleware:
        settings.MIDDLEWARE = ["django.middleware.clickjacking.XFrameOptionsMiddleware"]
    client = Client(enforce_csrf_checks=True)
    id = capture(plain())
    kwargs = {"id": id} if page == "sent" else {}

    response = client.get(route(page, **kwargs))
    # One token per form: Delete and Clear all.
    token = re.findall(
        r'name="csrfmiddlewaretoken" value="([^"]+)"', response.content.decode()
    )[0]
    posted = client.post(route(action, **kwargs), {"csrfmiddlewaretoken": token})

    assert "csrftoken" in response.cookies
    assert posted.status_code == 302
    assert FileStorage().list() == []


def test_latest_reports_the_count_and_the_newest_id(client):
    before = client.get(route("sent_latest"))
    id = capture(plain())
    after = client.get(route("sent_latest"))

    assert before["Content-Type"] == "application/json"
    assert before["Cache-Control"] == "no-store"
    assert before.json() == {"count": 0, "latest": None}
    assert after.json() == {"count": 1, "latest": id}


@pytest.mark.parametrize(
    ("name", "content_type"),
    [("preview.css", "text/css"), ("preview.js", "text/javascript")],
)
def test_assets_come_from_the_package(client, name, content_type):
    response = client.get(route("asset", name=name))

    assert response.status_code == 200
    assert response["Content-Type"] == content_type
    assert response["Cache-Control"] == "max-age=3600"
    assert (
        response.getvalue()
        == (views.PACKAGE / "static" / "django_mail_preview" / name).read_bytes()
    )


@pytest.mark.parametrize(
    "path",
    [
        "assets/preview.map",
        "assets/views.py",
        "assets/../views.py",
        "assets/preview.css/",
    ],
)
def test_other_assets_are_404(client, path):
    response = client.get(route("index") + path)

    assert response.status_code == 404


def test_pages_render_without_a_project_template_engine_or_frame_exemption(
    settings, client
):
    assert settings.TEMPLATES == []
    assert (
        "django.middleware.clickjacking.XFrameOptionsMiddleware" in settings.MIDDLEWARE
    )
    id = capture(html())

    page = client.get(route("sent", id=id))
    frame = client.get(route("sent_html", id=id))

    assert page.status_code == 200
    assert page["X-Frame-Options"] == "DENY"
    assert frame["X-Frame-Options"] == "SAMEORIGIN"


@csp_middleware
def test_own_policies_survive_the_csp_middleware(settings, client):
    settings.MIDDLEWARE = [
        *settings.MIDDLEWARE,
        "django.middleware.csp.ContentSecurityPolicyMiddleware",
    ]
    settings.SECURE_CSP = {"default-src": ["'self'"]}
    settings.SECURE_CSP_REPORT_ONLY = {"default-src": ["'self'"], "report-uri": "/csp/"}
    id = capture(html())

    page = client.get(route("sent", id=id))
    frame = client.get(route("sent_html", id=id))
    part = client.get(route("sent_part", id=id, n=0))
    eml = client.get(route("sent_eml", id=id))

    assert page["Content-Security-Policy"] == "default-src 'self'"
    assert (
        page["Content-Security-Policy-Report-Only"]
        == "default-src 'self'; report-uri /csp/"
    )
    assert frame["Content-Security-Policy"] == FRAME_CSP
    assert part["Content-Security-Policy"] == DOWNLOAD_CSP
    assert eml["Content-Security-Policy"] == DOWNLOAD_CSP
    for response in (frame, part, eml):
        assert "Content-Security-Policy-Report-Only" not in response
