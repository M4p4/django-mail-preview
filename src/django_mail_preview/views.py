"""The inbox and preview pages, the frame that shows an email's HTML, and the downloads.

Every view answers 404 unless the request may open the pages: while ``DEBUG``
is on, or when the ``MAIL_PREVIEW_ALLOW`` callable says so. Templates render
through the package's own engine, so a project without a Django template
backend works too.
"""

from __future__ import annotations

import base64
import functools
import importlib.metadata
from collections import Counter
from collections.abc import Callable
from email.utils import parseaddr
from pathlib import Path
from typing import Concatenate, ParamSpec, TypeVar

import django
from django.conf import settings
from django.http import (
    FileResponse,
    Http404,
    HttpRequest,
    HttpResponse,
    HttpResponseBase,
    HttpResponseRedirect,
    JsonResponse,
)
from django.middleware.csrf import get_token
from django.template import Context, Engine
from django.urls import reverse
from django.utils.http import content_disposition_header
from django.utils.module_loading import import_string
from django.views.decorators.clickjacking import xframe_options_sameorigin
from django.views.decorators.csrf import csrf_protect, ensure_csrf_cookie
from django.views.decorators.http import require_POST, require_safe

from django_mail_preview.backends import serialise
from django_mail_preview.checks import backend_is_active
from django_mail_preview.conf import mail_preview_settings
from django_mail_preview.message import ParsedMessage, parse, prepare_html
from django_mail_preview.registry import Preview, get_previews
from django_mail_preview.storage import (
    BaseStorage,
    FileStorage,
    MessageMeta,
    StoredMessage,
    get_storage,
)

__all__ = [
    "ASSETS",
    "DOWNLOAD_CSP",
    "FRAME_CSP",
    "TABS",
    "allowed",
    "asset",
    "index",
    "is_allowed",
    "neighbours",
    "preview",
    "preview_eml",
    "preview_html",
    "preview_part",
    "sent",
    "sent_clear",
    "sent_delete",
    "sent_eml",
    "sent_html",
    "sent_latest",
    "sent_part",
    "without_project_csp",
]

PACKAGE = Path(__file__).resolve().parent

FRAME_CSP = (
    "default-src 'none'; img-src data: http: https:; "
    "style-src 'unsafe-inline' http: https:; font-src data: http: https:; "
    "base-uri 'none'; frame-ancestors 'self'; "
    "sandbox allow-popups allow-popups-to-escape-sandbox"
)
"""The policy of an email's HTML in its frame.

Images, styles and fonts load from anywhere, as in a mail client, and the
message's own inline parts arrive as ``data:`` URIs (see ``frame``); scripts
never run, not even when the URL is opened directly, because ``sandbox``
applies to the navigation too. Schemes rather than ``'self'``, which has had
edge cases in sandboxed documents and which nothing in the frame needs.
``base-uri 'none'`` keeps an email's own ``<base>`` from rewriting relative
URLs.
"""

DOWNLOAD_CSP = "sandbox; default-src 'none'"
"""The policy of a part or ``.eml`` download: an SVG or HTML attachment opened directly can't run script in the site's origin."""

ASSETS = {
    "preview.css": "text/css",
    "preview.js": "text/javascript",
    "theme.js": "text/javascript",
}
"""The files ``asset`` serves, with explicit content types: the ``mimetypes`` registry isn't reliable on Windows."""

TABS = (
    ("html", "HTML"),
    ("text", "Plain text"),
    ("source", "Source"),
    ("headers", "Headers"),
    ("mime", "MIME"),
)

P = ParamSpec("P")
R = TypeVar("R", bound=HttpResponseBase)
V = TypeVar("V", bound=Callable[..., HttpResponseBase])


def is_allowed(request: HttpRequest) -> bool:
    """Whether the request may open the pages.

    ``MAIL_PREVIEW_ALLOW`` decides when it's set; otherwise only ``DEBUG`` opens
    them.
    """
    path = mail_preview_settings.ALLOW
    if path is None:
        return bool(settings.DEBUG)
    allow: Callable[[HttpRequest], object] = import_string(path)
    return bool(allow(request))


def allowed(
    view: Callable[Concatenate[HttpRequest, P], R],
) -> Callable[Concatenate[HttpRequest, P], R]:
    """Answer 404 unless the request may open the pages, so to anyone else the URLs don't exist."""

    @functools.wraps(view)
    def wrapper(request: HttpRequest, /, *args: P.args, **kwargs: P.kwargs) -> R:
        if not is_allowed(request):
            raise Http404("The mail preview pages are closed to this request.")
        return view(request, *args, **kwargs)

    return wrapper


def without_project_csp(view: V) -> V:
    """Keep a project's CSP middleware (Django 6.0 and later) off a response with its own policy.

    The middleware never replaces a ``Content-Security-Policy`` header the view
    set, but it would add the project's report-only policy, and every inline
    style in an email would then land in the project's report endpoint.
    """
    try:
        from django.views.decorators.csp import (
            csp_override,
            csp_report_only_override,
        )
    except ImportError:  # Django 5.2 has no CSP middleware.
        return view
    return csp_override({})(csp_report_only_override({})(view))


@functools.cache
def engine() -> Engine:
    """The package's own template engine, independent of the project's ``TEMPLATES``."""
    return Engine(dirs=[str(PACKAGE / "templates")], debug=settings.DEBUG)


def render(
    request: HttpRequest, template: str, context: dict[str, object]
) -> HttpResponse:
    """Render one of the package's templates.

    ``request`` and ``csrf_token`` are always in the context: the forms need
    the token, and ``{% csrf_token %}`` warns without it. ``version`` goes on
    the asset URLs, so an upgrade gets past the browser's cache.
    """
    context = {
        **context,
        "request": request,
        "csrf_token": get_token(request),
        "version": version(),
    }
    page = engine().get_template(f"django_mail_preview/{template}")
    return HttpResponse(page.render(Context(context)))


@functools.cache
def version() -> str:
    """The installed version of the package."""
    return importlib.metadata.version("django-mail-preview")


def sidebar(
    storage: BaseStorage,
    previews: list[Preview],
    messages: list[StoredMessage],
    current: str | None = None,
) -> dict[str, object]:
    """What every page's sidebar shows: the previews by group, the captured messages newest first, and the storage in use.

    ``messages`` is the storage's list, taken once per request; ``current`` is
    the id of the open preview or message, if any.
    """
    groups: dict[str, list[Preview]] = {}
    for preview in previews:
        groups.setdefault(preview.group, []).append(preview)
    path, cls = storage_location(storage)
    return {
        "previews": sorted(groups.items()),
        "sent": messages,
        "current": current,
        "storage_path": path,
        "storage_class": cls,
        "backend_active": backend_is_active(),
    }


def storage_location(storage: BaseStorage) -> tuple[str | None, str | None]:
    """Where captured mail lives: the file storage's directory, or the class
    of any other storage.

    It answers "where is my mail?" in the two places the question comes up,
    the empty start page and the Inbox heading's tooltip, and nowhere else.
    """
    if isinstance(storage, FileStorage):
        return str(storage.root), None
    return None, f"{type(storage).__module__}.{type(storage).__qualname__}"


def neighbours(messages: list[StoredMessage], id: str) -> tuple[str | None, str | None]:
    """The ids of the newer and the older neighbour of a message in the list, newest first.

    Ids, never positions, so the links stay right when mail arrives or is
    deleted in between. Either is ``None`` at that end of the list, both when
    the message isn't listed.
    """
    ids = [stored.meta.id for stored in messages]
    try:
        at = ids.index(id)
    except ValueError:
        return None, None
    newer = ids[at - 1] if at > 0 else None
    older = ids[at + 1] if at + 1 < len(ids) else None
    return newer, older


def captured(storage: BaseStorage, id: str) -> tuple[MessageMeta, bytes]:
    """A captured message's metadata and bytes; 404 when it's unknown or gone."""
    stored = storage.get(id)
    if stored is None or stored.raw is None:
        raise Http404(f"No captured message {id}.")
    return stored.meta, stored.raw


def find_preview(previews: list[Preview], group: str, name: str) -> Preview:
    """The preview at ``previews/<group>/<name>/``; 404 when there is none."""
    for preview in previews:
        if (preview.group, preview.method) == (group, name):
            return preview
    raise Http404(f"No preview {group}.{name}.")


def rendered(request: HttpRequest, group: str, name: str) -> bytes:
    """The message of the preview at ``previews/<group>/<name>/``, built for this request.

    Built on every request and never stored, so the query string reaches the
    preview's ``params`` in the frame and the downloads too. An error in the
    preview propagates: the debug page then points at the preview's own code.
    """
    return serialise(find_preview(get_previews(), group, name).render(request))


def query_string(request: HttpRequest) -> str:
    """The request's query string, with its ``?``, to pass a preview's ``params`` on to its frame and downloads."""
    return f"?{request.GET.urlencode()}" if request.GET else ""


def message_page(
    request: HttpRequest,
    parsed: ParsedMessage,
    *,
    html_url: str,
    eml_url: str,
    part_url: Callable[[int], str],
    context: dict[str, object],
) -> HttpResponse:
    """The page of a message, captured or previewed: the header, the tabs and the parts."""
    tab = request.GET.get("tab", "")
    if tab not in dict(TABS):
        tab = "html" if parsed.html is not None else "text"
    return render(
        request,
        "message.html",
        {
            **context,
            "parsed": parsed,
            "initial": initial(parsed.from_),
            "tab": tab,
            "tabs": [(name, label, tab_url(request, name)) for name, label in TABS],
            "html_url": html_url,
            "eml_url": eml_url,
            "parts": [(part, part_url(part.index)) for part in parsed.parts],
        },
    )


def initial(sender: str) -> str:
    """The avatar's letter: the first letter or digit of the sender's name, or of the address."""
    name, address = parseaddr(sender)
    return next((c.upper() for c in (name or address) if c.isalnum()), "?")


def tab_url(request: HttpRequest, tab: str) -> str:
    """The current page with ``?tab=`` set, keeping the other query parameters (a preview's ``params``)."""
    query = request.GET.copy()
    query["tab"] = tab
    return f"?{query.urlencode()}"


def frame(parsed: ParsedMessage) -> HttpResponse:
    """The HTML part, prepared for the sandboxed frame, under ``FRAME_CSP``.

    Inline parts are embedded as ``data:`` URIs rather than linked by their
    part URLs. The sandboxed frame has an opaque origin, so the browser sends no
    cookie with the requests it makes, and a cookie-based ``MAIL_PREVIEW_ALLOW``
    (``request.user.is_staff``, say) would answer every one of them with 404.
    """
    if parsed.html is None:
        raise Http404("The message has no HTML part.")
    by_cid = {
        part.content_id: part for part in parsed.parts if part.content_id is not None
    }

    def data_uri(cid: str) -> str | None:
        part = by_cid.get(cid)
        if part is None:
            return None
        encoded = base64.b64encode(part.content).decode("ascii")
        return f"data:{part.content_type};base64,{encoded}"

    response = HttpResponse(prepare_html(parsed.html, data_uri))
    response["Content-Security-Policy"] = FRAME_CSP
    # Keeps the message URL out of the logs behind tracking pixels.
    response["Referrer-Policy"] = "no-referrer"
    return response


def download(content: bytes, content_type: str, filename: str) -> HttpResponse:
    """A response the browser saves rather than shows, whatever its type."""
    disposition = content_disposition_header(as_attachment=True, filename=filename)
    assert disposition is not None  # Always set for an attachment.
    response = HttpResponse(content, content_type=content_type)
    response["Content-Disposition"] = disposition
    response["X-Content-Type-Options"] = "nosniff"
    response["Content-Security-Policy"] = DOWNLOAD_CSP
    return response


def part_download(parsed: ParsedMessage, n: int) -> HttpResponse:
    """Part ``n`` as a download named after the part, or ``part-<n>``."""
    try:
        part = parsed.parts[n]
    except IndexError:
        raise Http404(f"The message has no part {n}.") from None
    return download(part.content, part.content_type, part.filename or f"part-{n}")


def route(view: str, **kwargs: object) -> str:
    return reverse(f"mail_preview:{view}", kwargs=kwargs or None)


@allowed
@require_safe
# The page sets the cookie its forms' tokens are checked against, so the forms
# work whatever middleware the project has.
@ensure_csrf_cookie
def index(request: HttpRequest) -> HttpResponse:
    """The sidebar and, until a message is picked, what to do next."""
    storage = get_storage()
    messages = storage.list()
    context = sidebar(storage, get_previews(), messages)
    # The empty page's settings hint: MAILERS from Django 6.1, EMAIL_BACKEND before.
    context["mailers"] = django.VERSION >= (6, 1)
    # The search box's value, so a reload for new mail keeps the query.
    context["query"] = request.GET.get("q", "")
    # The chip row: every tag of the listed mail, with how many messages carry it.
    context["tags"] = sorted(
        Counter(tag for stored in messages for tag in stored.meta.tags).items()
    )
    return render(request, "index.html", context)


@allowed
@require_safe
def sent_latest(request: HttpRequest) -> HttpResponse:
    """What the page polls: the count and the newest id, enough to notice new mail."""
    messages = get_storage().list()
    latest = messages[0].meta.id if messages else None
    response = JsonResponse({"count": len(messages), "latest": latest})
    response["Cache-Control"] = "no-store"
    return response


@allowed
@require_safe
@ensure_csrf_cookie
def sent(request: HttpRequest, id: str) -> HttpResponse:
    storage = get_storage()
    meta, raw = captured(storage, id)
    messages = storage.list()
    newer, older = neighbours(messages, id)
    return message_page(
        request,
        parse(raw),
        html_url=route("sent_html", id=id),
        eml_url=route("sent_eml", id=id),
        part_url=lambda n: route("sent_part", id=id, n=n),
        context={
            **sidebar(storage, get_previews(), messages, current=id),
            "meta": meta,
            "bcc": meta.bcc,
            "delete_url": route("sent_delete", id=id),
            "newer_url": None if newer is None else route("sent", id=newer),
            "older_url": None if older is None else route("sent", id=older),
        },
    )


@allowed
@require_safe
@xframe_options_sameorigin
@without_project_csp
def sent_html(request: HttpRequest, id: str) -> HttpResponse:
    _, raw = captured(get_storage(), id)
    return frame(parse(raw))


@allowed
@require_safe
@without_project_csp
def sent_part(request: HttpRequest, id: str, n: str) -> HttpResponse:
    _, raw = captured(get_storage(), id)
    return part_download(parse(raw), int(n))


@allowed
@require_safe
@without_project_csp
def sent_eml(request: HttpRequest, id: str) -> HttpResponse:
    _, raw = captured(get_storage(), id)
    return download(raw, "message/rfc822", f"{id}.eml")


@allowed
@require_POST
@csrf_protect
def sent_delete(request: HttpRequest, id: str) -> HttpResponse:
    get_storage().delete(id)
    return HttpResponseRedirect(route("index"))


@allowed
@require_POST
@csrf_protect
def sent_clear(request: HttpRequest) -> HttpResponse:
    get_storage().clear()
    return HttpResponseRedirect(route("index"))


@allowed
@require_safe
@ensure_csrf_cookie
def preview(request: HttpRequest, group: str, name: str) -> HttpResponse:
    """The page of a preview, built for this request's query string."""
    previews = get_previews()
    found = find_preview(previews, group, name)
    message = found.render(request)
    query = query_string(request)
    storage = get_storage()
    return message_page(
        request,
        parse(serialise(message)),
        html_url=route("preview_html", group=group, name=name) + query,
        eml_url=route("preview_eml", group=group, name=name) + query,
        part_url=lambda n: route("preview_part", group=group, name=name, n=n) + query,
        context={
            **sidebar(storage, previews, storage.list(), current=found.id),
            "preview": found,
            # Only the message object knows them: Bcc is never serialised.
            "bcc": message.bcc,
        },
    )


@allowed
@require_safe
@xframe_options_sameorigin
@without_project_csp
def preview_html(request: HttpRequest, group: str, name: str) -> HttpResponse:
    return frame(parse(rendered(request, group, name)))


@allowed
@require_safe
@without_project_csp
def preview_part(request: HttpRequest, group: str, name: str, n: int) -> HttpResponse:
    return part_download(parse(rendered(request, group, name)), n)


@allowed
@require_safe
@without_project_csp
def preview_eml(request: HttpRequest, group: str, name: str) -> HttpResponse:
    return download(
        rendered(request, group, name), "message/rfc822", f"{group}.{name}.eml"
    )


@allowed
@require_safe
def asset(request: HttpRequest, name: str) -> HttpResponseBase:
    """``preview.css`` or ``preview.js`` from the package, so ``staticfiles`` isn't needed."""
    if name not in ASSETS:
        raise Http404(f"No asset {name}.")
    path = PACKAGE / "static" / "django_mail_preview" / name
    response = FileResponse(path.open("rb"), content_type=ASSETS[name])
    response["Cache-Control"] = "max-age=3600"
    return response
