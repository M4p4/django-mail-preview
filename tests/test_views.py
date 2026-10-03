from __future__ import annotations

import re
from base64 import b64encode
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from importlib.metadata import version
from unittest.mock import Mock

import django
import pytest
from django.core.mail import EmailMessage, EmailMultiAlternatives
from django.test import Client
from django.urls import reverse

from django_mail_preview import EmailPreview, views
from django_mail_preview.backends import EmailBackend
from django_mail_preview.checks import BACKEND
from django_mail_preview.storage import FileStorage, new_id
from tests.helpers import LATE_PREVIEWS, PNG, inline_image

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
OLD = datetime(2025, 1, 2, 12, 0, tzinfo=timezone.utc)
KEY = "open-sesame"
SAMPLE = {"group": "tests", "name": "html"}
"""The sample preview with an inline image and an attachment, from ``tests/previews.py``."""

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
    "preview": lambda id: route("preview", **SAMPLE),
    "preview_html": lambda id: route("preview_html", **SAMPLE),
    "preview_part": lambda id: route("preview_part", n=0, **SAMPLE),
    "preview_eml": lambda id: route("preview_eml", **SAMPLE),
    "asset": lambda id: route("asset", name="preview.css"),
}

BY_ID = [("sent", {}), ("sent_html", {}), ("sent_part", {"n": 0}), ("sent_eml", {})]

BY_PREVIEW = [
    ("preview", {}),
    ("preview_html", {}),
    ("preview_part", {"n": 0}),
    ("preview_eml", {}),
]

kinds = pytest.mark.parametrize("kind", ["sent", "preview"])


def allow_with_key(request):
    """A MAIL_PREVIEW_ALLOW callable: opens the pages to requests that know the key."""
    return request.headers.get("X-Key") == KEY


def route(view, **kwargs):
    return reverse(f"mail_preview:{view}", kwargs=kwargs or None)


def plain(subject="Hello"):
    return EmailMessage(subject, "Hi there.", "sender@example.com", ["to@example.com"])


def tagged(subject, *tags):
    """A plain message with an ``X-Tags`` header."""
    return EmailMessage(
        subject,
        "Hi there.",
        "sender@example.com",
        ["to@example.com"],
        headers={"X-Tags": ", ".join(tags)},
    )


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


def urls(kind):
    """The page, frame, first-part and ``.eml`` URLs of an HTML message of either kind.

    A captured message, or the ``tests.html`` sample preview; part 0 of both is
    the inline PNG.
    """
    kwargs = {"id": capture(html())} if kind == "sent" else SAMPLE
    return {
        "page": route(kind, **kwargs),
        "html": route(f"{kind}_html", **kwargs),
        "part": route(f"{kind}_part", n=0, **kwargs),
        "eml": route(f"{kind}_eml", **kwargs),
    }


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


def test_index_lists_captured_mail_as_a_table_newest_first(client):
    first = capture(plain("First"))
    second = capture(html("Second"))

    response = client.get(route("index"))

    content = response.content.decode()
    assert response.status_code == 200
    # Once in the sidebar heading, once in the page heading.
    assert content.count('Inbox <span class="count">2</span>') == 2
    assert content.index(route("sent", id=second)) < content.index(
        route("sent", id=first)
    )
    rows = re.findall(r"<tr>\s*<td>(.*?)</tr>", content, re.S)
    assert len(rows) == 2
    assert f'<a href="{route("sent", id=second)}">Second</a>' in rows[0]
    assert '<td class="from wide">sender@example.com</td>' in rows[0]
    assert '<td class="to">to@example.com</td>' in rows[0]
    assert 'title="2 attachments"' in rows[0]
    assert re.search(r'<td class="wide num">[\d.]+\xa0(bytes|KB)</td>', rows[0])
    assert re.search(
        r'<time class="ago" datetime="[^"]+" title="[^"]+">just now</time>', rows[0]
    )
    assert '<span class="clip"' not in rows[1]
    assert "Nothing captured yet." not in content
    assert 'name="csrfmiddlewaretoken"' in content
    # Where the mail lives is a tooltip on the heading, not a line of its own.
    assert f'<h2 title="Stored in {FileStorage().root}">' in content
    assert "<footer" not in content


def test_index_has_the_search_box_with_its_operators(client):
    capture(plain())

    content = client.get(route("index")).content.decode()

    assert '<form class="search" role="search">' in content
    assert (
        '<input type="search" name="q" id="q" value="" '
        'placeholder="Search · from: to: subject: has:attachment tag:"' in content
    )
    assert '<button type="button" class="clear"' in content
    assert '<p class="nomatch" hidden>No messages match.</p>' in content


def test_index_prefills_the_search_box_from_the_url(client):
    capture(plain())

    content = client.get(route("index"), {"q": 'from:"a" <b>'}).content.decode()

    assert 'value="from:&quot;a&quot; &lt;b&gt;"' in content


def test_index_lists_the_tags_with_their_counts(client):
    capture(plain("Untagged"))
    receipt = capture(tagged("Receipt", "billing"))
    welcome = capture(tagged("Welcome", "onboarding", "Billing"))

    content = client.get(route("index")).content.decode()

    chip = '<button type="button" class="tag" data-tag="{0}" aria-pressed="false">{0}</button>'
    [bar] = re.findall(
        r'<div class="tagbar" role="group" aria-label="Filter by tag">(.*?)</div>',
        content,
        re.S,
    )
    assert re.findall(r'data-tag="(\w+)"[^>]*>\w+ <span class="count">(\d+)', bar) == [
        ("billing", "2"),
        ("onboarding", "1"),
    ]
    # Under the subject in the table, sorted; the row carries them for the script.
    cells = re.findall(r"<tr[^>]*>\s*<td>(.*?)</td>", content, re.S)
    assert cells[0] == (
        f'<a href="{route("sent", id=welcome)}">Welcome</a><span class="tags">'
        f"{chip.format('billing')}{chip.format('onboarding')}</span>"
    )
    assert cells[1] == (
        f'<a href="{route("sent", id=receipt)}">Receipt</a>'
        f'<span class="tags">{chip.format("billing")}</span>'
    )
    assert 'class="tag"' not in cells[2]
    body = content.split("<tbody>")[1]
    assert re.findall(r"<tr( data-tags=\"[^\"]*\")?>", body) == [
        ' data-tags="billing onboarding"',
        ' data-tags="billing"',
        "",
    ]
    # Plain spans on the sidebar rows.
    assert (
        '<span class="tags"><span class="tag">billing</span>'
        '<span class="tag">onboarding</span></span>' in content
    )
    assert content.count('<span class="tags"><span class="tag">') == 2


def test_sidebar_row_shows_two_tags_and_counts_the_rest(client):
    capture(tagged("Statement", "renewal", "billing", "finance", "quarterly", "vip"))

    content = client.get(route("index")).content.decode()

    assert (
        '<span class="tags"><span class="tag">billing</span><span class="tag">finance</span>'
        '<span class="tag more" title="quarterly, renewal, vip">+3</span></span>'
        in content
    )
    # The table row shows three and counts the rest, but carries all five.
    assert (
        '<span class="tag more" data-tags="renewal vip" title="renewal, vip" '
        'aria-pressed="false">+2</span></span></td>' in content
    )
    assert content.count('<button type="button" class="tag"') == 5 + 3
    assert 'data-tags="billing finance quarterly renewal vip"' in content


def test_index_without_tags_has_no_tag_row(client):
    capture(plain())

    content = client.get(route("index")).content.decode()

    assert 'class="tagbar"' not in content
    assert 'class="tag"' not in content
    assert 'class="tags"' not in content


def test_index_escapes_a_tag_with_markup(client):
    capture(tagged("Hi", "<b>"))

    content = client.get(route("index")).content.decode()

    assert 'data-tag="&lt;b&gt;" aria-pressed="false">&lt;b&gt;' in content
    assert "<b>" not in content


def test_message_page_links_each_tag_to_the_filtered_inbox(client):
    id = capture(tagged("Receipt", "billing", "q&a"))

    content = client.get(route("sent", id=id)).content.decode()

    assert (
        f'<p class="tags"><a class="tag" href="{route("index")}?q=tag:billing">billing</a>'
        f'<a class="tag" href="{route("index")}?q=tag:q%26a">q&amp;a</a></p>' in content
    )
    # Under the addresses, inside the sender block, not under the subject.
    assert content.index('class="route"') < content.index('<p class="tags">')
    assert content.index('<p class="tags">') < content.index('class="aside"')


def test_index_escapes_a_subject_with_markup(client):
    capture(plain("<b>Bold</b> & co"))

    content = client.get(route("index")).content.decode()

    assert "&lt;b&gt;Bold&lt;/b&gt; &amp; co" in content
    assert "<b>Bold</b>" not in content


def test_index_without_mail_shows_the_empty_inbox_instead_of_the_table(client):
    content = client.get(route("index")).content.decode()

    assert "<table" not in content
    assert 'class="search"' not in content
    assert "<h1>Your inbox is empty</h1>" in content
    assert '<button type="button" class="copy">' in content
    # The storage lives in the heading's tooltip only.
    assert "Captured mail is stored in" not in content


def test_sidebar_shows_the_time_for_today_and_the_date_for_older_mail(client):
    storage = FileStorage()
    capture(plain("Recent"))
    recent = storage.list()[0].meta
    old = replace(recent, id=new_id(OLD), subject="Old", date=OLD)
    storage.add(b"Subject: Old\r\n\r\nHi.\r\n", old)

    content = client.get(route("index")).content.decode()

    assert re.search(r'<time datetime="[^"]+" title="[^"]+">\d\d:\d\d</time>', content)
    assert ">Jan 2</time>" in content
    # The paperclip only shows with attachments: neither message has any.
    assert '<span class="clip"' not in content


def test_table_says_how_long_ago_mail_arrived_and_the_sidebar_does_not(client):
    storage = FileStorage()
    capture(plain("Recent"))
    recent = storage.list()[0].meta
    then = datetime.now(timezone.utc) - timedelta(days=3, hours=2)
    old = replace(recent, id=new_id(then), subject="Old", date=then)
    storage.add(b"Subject: Old\r\n\r\nHi.\r\n", old)

    content = client.get(route("index")).content.decode()

    # Once each: the table cell, with the exact time in its tooltip. The
    # sidebar keeps the time of day or the date.
    assert content.count(">just now</time>") == 1
    assert content.count(">3 days ago</time>") == 1
    assert re.search(
        r'<time class="ago" datetime="[^"]+" title="[^"]+">3 days ago</time>', content
    )
    assert 'class="ago"' not in content.split('<main class="pane">')[0]


def test_sidebar_shows_the_attachment_count(client):
    capture(html())

    content = client.get(route("index")).content.decode()

    # Once in the sidebar, once in the table.
    assert content.count('<span class="clip" title="2 attachments">') == 2


def test_top_bar_button_controls_the_sidebar(client):
    content = client.get(route("index")).content.decode()

    assert (
        '<button type="button" class="menu" aria-controls="sidebar" '
        'aria-expanded="false">Menu</button>' in content
    )
    assert '<aside class="sidebar" id="sidebar">' in content
    assert '<div class="scrim" hidden></div>' in content


def test_index_hints_at_the_backend_until_it_is_active(settings, client):
    """The one command on the empty page: the setting first, then a message to send."""
    setting = "MAILERS = {" if django.VERSION >= (6, 1) else 'EMAIL_BACKEND = "'
    command = 'python manage.py shell -c "from django.core.mail import send_mail;'

    before = client.get(route("index")).content.decode()
    settings.MAILERS = {"default": {"BACKEND": BACKEND}}
    after = client.get(route("index")).content.decode()

    assert setting in before and BACKEND in before
    assert command not in before
    assert command in after
    assert BACKEND not in after


def test_inbox_heading_names_a_custom_storage(settings, client):
    settings.MAIL_PREVIEW_STORAGE = "tests.test_storage.MemoryStorage"

    content = client.get(route("index")).content.decode()

    assert '<h2 title="Stored by tests.test_storage.MemoryStorage">' in content
    assert "tests.test_storage.MemoryStorage</code>" not in content


def test_inbox_heading_names_its_directory(client):
    """The tooltip carries the whole path, so a worker in another container can be pointed there."""
    root = FileStorage().root

    content = client.get(route("index")).content.decode()

    assert f'<h2 title="Stored in {root}">' in content
    assert f"<code>{root}</code>" not in content


def test_message_page(client):
    id = capture(html())

    response = client.get(route("sent", id=id))

    content = response.content.decode()
    assert response.status_code == 200
    assert "<title>Welcome · Mail Preview</title>" in content
    for address in ("sender", "to", "cc", "bcc", "reply"):
        assert f"{address}@example.com" in content
    assert f'<iframe src="{route("sent_html", id=id)}"' in content
    assert route("sent_eml", id=id) in content
    assert route("sent_delete", id=id) in content
    assert 'name="csrfmiddlewaretoken"' in content
    # The parts: the attachment, and the inline image without a filename.
    assert route("sent_part", id=id, n=1) in content
    assert "report.svg" in content
    assert "part-0" in content
    # Once in the parts list, once in the MIME tree.
    assert content.count('<span class="label">inline</span>') == 2
    # The header: the sender's initial and the date.
    assert '<span class="avatar" aria-hidden="true">S</span>' in content
    assert '<time class="date"' in content
    # The open message in the sidebar, and the current tab.
    assert content.count('aria-current="page"') == 2


def test_tabs_show_text_and_headers(client):
    id = capture(plain())

    response = client.get(route("sent", id=id))

    content = response.content.decode()
    assert "The message has no HTML part." in content
    assert "<pre>Hi there." in content
    assert '<th scope="row">Message-ID</th>' in content


def test_source_is_on_the_page_only_when_asked_for(client):
    """The source carries every attachment base64-encoded, so the other tabs don't ship it."""
    id = capture(html())

    page = client.get(route("sent", id=id))
    source = client.get(route("sent", id=id) + "?tab=source")

    # The first line of the attachment's base64 body.
    encoded = b64encode(SVG).decode()[:76]
    assert encoded not in page.content.decode()
    assert 'data-tab="source"' in page.content.decode()  # The tab link stays.
    assert "Subject: Welcome" in source.content.decode()
    assert encoded in source.content.decode()
    assert current_tab(source) == "source"


@pytest.mark.parametrize(
    ("build", "query", "tab"),
    [
        (html, "", "html"),
        (plain, "", "text"),
        (html, "?tab=text", "text"),
        (html, "?tab=source", "source"),
        (plain, "?tab=headers", "headers"),
        (plain, "?tab=mime", "mime"),
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


@kinds
def test_frame_serves_the_prepared_html_under_its_own_policy(client, kind):
    response = client.get(urls(kind)["html"])

    content = response.content.decode()
    assert response.status_code == 200
    assert response["Content-Type"] == "text/html; charset=utf-8"
    assert response["Content-Security-Policy"] == FRAME_CSP
    assert response["X-Frame-Options"] == "SAMEORIGIN"
    assert response["Referrer-Policy"] == "no-referrer"
    assert '<base target="_blank">' in content
    assert f'<img src="data:image/png;base64,{b64encode(PNG).decode()}"' in content


def test_frame_injects_the_base_into_the_head(client):
    id = capture(html())

    response = client.get(route("sent_html", id=id))

    assert response.content.startswith(b'<html><head><base target="_blank"></head>')


@kinds
def test_frame_embeds_inline_parts_so_it_makes_no_gated_request(settings, client, kind):
    """The sandboxed frame has an opaque origin and sends no cookie, so a cookie-based gate would 404 its part requests."""
    pages = urls(kind)
    settings.MAIL_PREVIEW_ALLOW = "tests.test_views.allow_with_key"

    response = client.get(pages["html"], headers={"X-Key": KEY})

    content = response.content.decode()
    assert response.status_code == 200
    assert "data:image/png;base64," in content
    assert pages["part"] not in content


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
    [
        ("preview.css", "text/css"),
        ("preview.js", "text/javascript"),
        ("theme.js", "text/javascript"),
    ],
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


def test_asset_urls_carry_the_package_version(client):
    response = client.get(route("index"))

    content = response.content.decode()
    for name in ("preview.css", "preview.js", "theme.js"):
        assert (
            f"{route('asset', name=name)}?v={version('django-mail-preview')}" in content
        )


def test_theme_script_blocks_in_the_head_ahead_of_the_stylesheet(client):
    """The stored scheme lands on ``<html>`` before anything paints."""
    content = client.get(route("index")).content.decode()

    script = f'<script src="{route("asset", name="theme.js")}?v={version("django-mail-preview")}"></script>'
    assert script in content
    assert content.index(script) < content.index('<link rel="stylesheet"')
    assert content.index(script) < content.index("<body")


@kinds
def test_theme_button_is_in_the_sidebar_and_the_top_bar(client, kind):
    pages = [client.get(route("index")), client.get(urls(kind)["page"])]

    for response in pages:
        content = response.content.decode()
        buttons = re.findall(r'<button type="button" class="icon theme"[^>]*>', content)
        assert len(buttons) == 2
        assert all('aria-label="Switch to dark mode"' in button for button in buttons)
        assert content.count('class="i moon"') == 2
        assert content.count('class="i sun"') == 2


def test_stylesheet_carries_the_dark_tokens_for_the_system_and_for_the_choice(client):
    css = client.get(route("asset", name="preview.css")).getvalue().decode()

    assert ':root:not([data-theme="light"])' in css
    assert ':root[data-theme="dark"]' in css
    assert ':root[data-theme="light"]' in css


@kinds
def test_pages_have_no_inline_script_style_or_handler(client, kind):
    """A strict CSP needs no nonce for the pages: both scripts have a ``src``."""
    pages = urls(kind)
    rendered = [
        client.get(route("index")).content.decode(),
        client.get(pages["page"]).content.decode(),
        client.get(pages["page"] + "?tab=source").content.decode(),
    ]
    templates = [
        path.read_text()
        for path in (views.PACKAGE / "templates" / "django_mail_preview").iterdir()
    ]

    for content in rendered + templates:
        assert re.findall(r"<script\b(?![^>]*\bsrc=)", content) == []
        assert "<style" not in content
        assert re.findall(r"<[^>]*\son\w+\s*=", content) == []


def test_body_carries_what_the_live_list_compares_with(client):
    empty = client.get(route("index"))
    id = capture(plain())
    index = client.get(route("index"))
    message = client.get(route("sent", id=id))

    assert (
        f'<body data-page="index" data-latest-url="{route("sent_latest")}" '
        'data-count="0" data-latest="">' in empty.content.decode()
    )
    assert f'data-count="1" data-latest="{id}"' in index.content.decode()
    assert '<body data-page="message"' in message.content.decode()
    assert "New mail · refresh" in message.content.decode()


@pytest.mark.parametrize(("build", "shown"), [(html, True), (plain, False)])
def test_frame_toolbar_comes_with_the_html_part(client, build, shown):
    id = capture(build())

    response = client.get(route("sent", id=id))

    content = response.content.decode()
    assert ('aria-label="Frame width"' in content) is shown
    assert ('aria-label="Width in pixels"' in content) is shown
    assert (
        f'<a href="{route("sent_html", id=id)}" target="_blank" rel="noopener"'
        in content
    ) is shown


def test_download_link_is_on_every_tab(client):
    id = capture(plain())

    for tab in ("text", "headers", "mime", "source"):
        response = client.get(route("sent", id=id) + f"?tab={tab}")

        assert (
            f'<a href="{route("sent_eml", id=id)}" class="icon" '
            'title="Download .eml" aria-label="Download .eml">'
            in response.content.decode()
        )


def test_neighbour_links_lead_to_the_newer_and_the_older_message(client):
    oldest = capture(plain("Oldest"))
    middle = capture(plain("Middle"))
    newest = capture(plain("Newest"))

    pages = {
        id: client.get(route("sent", id=id)).content.decode()
        for id in (oldest, middle, newest)
    }

    newer = '<a href="{}" rel="prev" class="icon" title="Newer message" aria-label="Newer message">'
    older = '<a href="{}" rel="next" class="icon" title="Older message" aria-label="Older message">'
    assert newer.format(route("sent", id=newest)) in pages[middle]
    assert older.format(route("sent", id=oldest)) in pages[middle]
    assert older.format(route("sent", id=middle)) in pages[newest]
    assert newer.format(route("sent", id=middle)) in pages[oldest]
    # An end of the list keeps the icon, without a link.
    assert 'rel="prev"' not in pages[newest]
    assert 'rel="next"' not in pages[oldest]
    assert (
        '<span class="icon" aria-disabled="true" title="No newer message">'
        in pages[newest]
    )
    assert (
        '<span class="icon" aria-disabled="true" title="No older message">'
        in pages[oldest]
    )
    assert "aria-disabled" not in pages[middle]


def test_neighbours_of_an_unlisted_message():
    """A storage whose list leaves the message out: no links rather than an error."""
    assert views.neighbours([], UNKNOWN_ID) == (None, None)


def test_preview_page_has_no_neighbour_links(client):
    content = client.get(route("preview", **SAMPLE)).content.decode()

    assert 'class="nav"' not in content
    assert 'rel="prev"' not in content
    assert 'rel="next"' not in content


def test_mime_tab_shows_the_tree(client):
    id = capture(html())

    response = client.get(route("sent", id=id) + "?tab=mime")

    content = response.content.decode()
    [section] = re.findall(
        r'<section class="tab" data-tab="mime">(.*?)</section>', content, re.S
    )
    assert current_tab(response) == "mime"
    assert re.findall(r"<code>([^<]+)</code>", section) == [
        "multipart/mixed",
        "multipart/alternative",
        "text/plain",
        "text/html",
        "image/png",
        "image/svg+xml",
    ]
    # Two containers, so two nested lists; a size on each of the four leaves.
    assert section.count("<ul>") == 2
    assert section.count('<span class="size">') == 4
    assert '<span class="label">inline</span>' in section
    assert '<span class="label">attachment</span>' in section
    assert '<span class="name">report.svg</span>' in section
    assert f'<span class="size">{len(SVG)}\xa0bytes</span>' in section


def test_copy_buttons_sit_on_the_text_and_source_tabs(client):
    id = capture(html())

    page = client.get(route("sent", id=id)).content.decode()
    source = client.get(route("sent", id=id) + "?tab=source").content.decode()

    button = '<button type="button" class="copy">'
    # Plain text only: the Source pane isn't on the page until asked for.
    assert page.count(button) == 1
    assert source.count(button) == 2
    [text] = re.findall(
        r'<section class="tab" data-tab="text" hidden>(.*?)</section>', page, re.S
    )
    assert button in text
    assert "<pre>Hi there." in text


def test_no_copy_button_without_a_plain_text_part(client):
    message = EmailMessage("Hi", "<p>Hi</p>", "sender@example.com", ["to@example.com"])
    message.content_subtype = "html"
    id = capture(message)

    content = client.get(route("sent", id=id)).content.decode()

    assert 'class="copy"' not in content
    assert "The message has no plain-text part." in content


@pytest.mark.parametrize(
    ("sender", "letter"),
    [
        ("sender@example.com", "S"),
        ('"Ada Lovelace" <ada@example.com>', "A"),
        ("'ops' <ops@example.com>", "O"),
        ("Émile <emile@example.com>", "É"),
        ("", "?"),
    ],
)
def test_initial_is_the_first_letter_of_the_sender(sender, letter):
    assert views.initial(sender) == letter


def test_pages_carry_the_wordmark_and_the_favicon(client):
    content = client.get(route("index")).content.decode()

    assert '<link rel="icon" href="data:image/svg+xml,' in content
    # In the sidebar and in the top bar, without a version number beside the name.
    assert content.count('class="wordmark"') == 2
    assert content.count('<span class="name">Mail Preview</span>') == 2
    assert "<title>Mail Preview</title>" in content
    assert 'class="version"' not in content
    assert version("django-mail-preview") not in content.replace(
        f"?v={version('django-mail-preview')}", ""
    )


def test_index_explains_how_to_add_previews_until_there_are_some(
    client, preview_registry
):
    with_previews = client.get(route("index"))
    preview_registry.clear()
    without = client.get(route("index"))

    guide = 'href="https://django-mail-preview.readthedocs.io/en/stable/previews.html"'
    assert guide not in with_previews.content.decode()
    assert guide in without.content.decode()
    assert "No previews yet? <a" in without.content.decode()


@kinds
def test_pages_render_without_a_project_template_engine_or_frame_exemption(
    settings, client, kind
):
    assert settings.TEMPLATES == []
    assert (
        "django.middleware.clickjacking.XFrameOptionsMiddleware" in settings.MIDDLEWARE
    )
    pages = urls(kind)

    page = client.get(pages["page"])
    frame = client.get(pages["html"])

    assert page.status_code == 200
    assert page["X-Frame-Options"] == "DENY"
    assert frame["X-Frame-Options"] == "SAMEORIGIN"


@csp_middleware
@kinds
def test_own_policies_survive_the_csp_middleware(settings, client, kind):
    settings.MIDDLEWARE = [
        *settings.MIDDLEWARE,
        "django.middleware.csp.ContentSecurityPolicyMiddleware",
    ]
    settings.SECURE_CSP = {"default-src": ["'self'"]}
    settings.SECURE_CSP_REPORT_ONLY = {"default-src": ["'self'"], "report-uri": "/csp/"}
    pages = urls(kind)

    page = client.get(pages["page"])
    frame = client.get(pages["html"])
    part = client.get(pages["part"])
    eml = client.get(pages["eml"])

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


@pytest.mark.parametrize(
    ("name", "subject", "tab"),
    [
        ("plain", "Welcome", "text"),
        ("html", "Welcome", "html"),
        ("greeting", "Hello Ada", "text"),
    ],
)
def test_preview_page(client, name, subject, tab):
    response = client.get(route("preview", group="tests", name=name))

    content = response.content.decode()
    assert response.status_code == 200
    assert f"<title>{subject} · Mail Preview</title>" in content
    assert "noreply@example.com" in content
    assert "ada@example.com" in content
    assert f"<code>tests.{name}</code>" in content
    assert route("preview_eml", group="tests", name=name) in content
    assert current_tab(response) == tab
    # The open preview in the sidebar, and the current tab; no date, no Delete.
    assert content.count('aria-current="page"') == 2
    assert '<time class="date"' not in content
    assert 'data-confirm="Delete this message?"' not in content


def test_preview_page_lists_the_parts(client):
    response = client.get(route("preview", **SAMPLE))

    content = response.content.decode()
    assert f'<iframe src="{route("preview_html", **SAMPLE)}"' in content
    assert route("preview_part", n=1, **SAMPLE) in content
    assert "terms.txt" in content
    assert route("preview_part", n=0, **SAMPLE) in content
    assert "part-0" in content


@pytest.mark.parametrize(
    ("name", "description"),
    [
        ("html", "A welcome with an inline logo and an attachment."),
        ("greeting", "Greets in the language of ``?lang=``, English unless given."),
    ],
)
def test_preview_page_shows_the_docstring(client, name, description):
    response = client.get(route("preview", group="tests", name=name))

    assert f'<p class="description">{description}</p>' in response.content.decode()


def test_preview_without_a_docstring_has_no_description(client):
    response = client.get(route("preview", group="tests", name="plain"))

    assert 'class="description"' not in response.content.decode()


def test_preview_page_shows_bcc(client):
    class Copies(EmailPreview):
        group = "copies"

        def blind(self):
            return EmailMessage(
                "Hi",
                "Hi.",
                "sender@example.com",
                ["to@example.com"],
                bcc=["bcc@example.com"],
            )

    response = client.get(route("preview", group="copies", name="blind"))

    assert "<span>bcc bcc@example.com</span>" in response.content.decode()


def test_params_reach_the_preview(client):
    english = client.get(route("preview", group="tests", name="greeting"))
    german = client.get(route("preview", group="tests", name="greeting") + "?lang=de")

    assert "<title>Hello Ada · Mail Preview</title>" in english.content.decode()
    assert "<title>Hallo Ada · Mail Preview</title>" in german.content.decode()


def test_params_are_passed_on_to_the_frame_and_the_downloads(client):
    response = client.get(route("preview", **SAMPLE) + "?lang=de&tab=source")

    content = response.content.decode()
    assert current_tab(response) == "source"
    assert (
        f'<iframe src="{route("preview_html", **SAMPLE)}?lang=de&amp;tab=source"'
        in content
    )
    assert f'href="{route("preview_eml", **SAMPLE)}?lang=de&amp;tab=source"' in content
    assert (
        f'href="{route("preview_part", n=1, **SAMPLE)}?lang=de&amp;tab=source"'
        in content
    )
    assert 'href="?lang=de&amp;tab=headers"' in content


def test_preview_downloads_are_rendered_with_their_params(client):
    response = client.get(
        route("preview_eml", group="tests", name="greeting") + "?lang=de"
    )

    assert b"Subject: Hallo Ada" in response.content


@pytest.mark.parametrize(
    ("n", "content_type", "disposition", "body"),
    [
        (0, "image/png", 'attachment; filename="part-0"', PNG),
        (1, "text/plain", 'attachment; filename="terms.txt"', b"The terms."),
    ],
)
def test_preview_parts_download(client, n, content_type, disposition, body):
    response = client.get(route("preview_part", n=n, **SAMPLE))

    assert response.status_code == 200
    assert response["Content-Type"] == content_type
    assert response["Content-Disposition"] == disposition
    assert response["X-Content-Type-Options"] == "nosniff"
    assert response["Content-Security-Policy"] == DOWNLOAD_CSP
    # Django 6's email API ends a text part with a newline; 5.2's doesn't.
    assert response.content.rstrip(b"\r\n") == body


def test_preview_eml_is_the_rendered_message(client):
    response = client.get(route("preview_eml", group="tests", name="plain"))

    assert response.status_code == 200
    assert response["Content-Type"] == "message/rfc822"
    assert response["Content-Disposition"] == 'attachment; filename="tests.plain.eml"'
    assert response["X-Content-Type-Options"] == "nosniff"
    assert response["Content-Security-Policy"] == DOWNLOAD_CSP
    assert b"\r\nSubject: Welcome\r\n" in response.content
    assert b"Hello Ada." in response.content


def test_preview_frame_of_a_message_without_html_is_404(client):
    response = client.get(route("preview_html", group="tests", name="plain"))

    assert response.status_code == 404


def test_preview_part_beyond_the_last_is_404(client):
    response = client.get(route("preview_part", n=2, **SAMPLE))

    assert response.status_code == 404


@pytest.mark.parametrize(("name", "kwargs"), BY_PREVIEW)
@pytest.mark.parametrize(
    ("group", "method"),
    [
        ("nope", "html"),
        ("tests", "nope"),
        ("tests", "GREETINGS"),
        ("tests", "request"),
        ("tests", "__init__"),
        ("tests.html", "html"),
    ],
)
def test_unknown_preview_is_404(client, name, kwargs, group, method):
    response = client.get(route(name, group=group, name=method, **kwargs))

    assert response.status_code == 404


def test_previews_are_never_stored(client, mail_preview_root):
    for name, kwargs in BY_PREVIEW:
        client.get(route(name, **kwargs, **SAMPLE))

    assert FileStorage().list() == []
    assert list(mail_preview_root.iterdir()) == []


def test_error_in_a_preview_propagates(client):
    """Nothing is caught, so the debug page points at the preview's own code."""

    class Broken(EmailPreview):
        group = "broken"

        def boom(self):
            raise RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        client.get(route("preview", group="broken", name="boom"))


def test_sidebar_lists_previews_by_group(client):
    """Groups come sorted, each with its previews sorted; the methods are only listed, never called."""

    class Shop(EmailPreview):
        group = "shop"

        def order(self): ...

    class Accounts(EmailPreview):
        group = "accounts"

        def welcome(self): ...

    response = client.get(route("index"))

    content = response.content.decode()
    assert re.findall(r'<details class="group" data-group="(\w+)" open>', content) == [
        "accounts",
        "shop",
        "tests",
    ]
    assert '<summary>accounts <span class="count">1</span></summary>' in content
    # The method name is the link; the id stays in the tooltip.
    assert (
        f'<a href="{route("preview", group="shop", name="order")}" '
        'title="shop.order">order</a>' in content
    )
    assert (
        content.index('title="accounts.welcome"')
        < content.index('title="shop.order"')
        < content.index('title="tests.greeting"')
        < content.index('title="tests.html"')
    )
    assert "No previews yet." not in content


def test_sidebar_without_previews(client, preview_registry):
    preview_registry.clear()

    response = client.get(route("index"))

    content = response.content.decode()
    assert "No previews yet." in content
    assert "<details" not in content


def test_previews_module_created_after_start_appears_on_the_next_request(
    client, late_app
):
    before = client.get(route("index"))
    (late_app / "previews.py").write_text(LATE_PREVIEWS)
    after = client.get(route("index"))
    page = client.get(route("preview", group="lateapp", name="welcome"))

    assert "lateapp.welcome" not in before.content.decode()
    assert "lateapp.welcome" in after.content.decode()
    assert page.status_code == 200
    assert "<title>Late · Mail Preview</title>" in page.content.decode()
