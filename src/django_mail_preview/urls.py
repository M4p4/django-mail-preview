"""The inbox URLs; include them under any prefix, ``__mail-preview__/`` by convention."""

from __future__ import annotations

from django.urls import path, re_path

from django_mail_preview import views
from django_mail_preview.storage import MESSAGE_ID

app_name = "mail_preview"

# The id routes spell out the id pattern, so a malformed id is a 404 from the
# resolver and sent/clear/ can't be taken for an id.
urlpatterns = [
    path("", views.index, name="index"),
    path("sent/latest/", views.sent_latest, name="sent_latest"),
    path("sent/clear/", views.sent_clear, name="sent_clear"),
    re_path(rf"^sent/(?P<id>{MESSAGE_ID})/$", views.sent, name="sent"),
    re_path(rf"^sent/(?P<id>{MESSAGE_ID})/html/$", views.sent_html, name="sent_html"),
    re_path(
        rf"^sent/(?P<id>{MESSAGE_ID})/parts/(?P<n>[0-9]+)/$",
        views.sent_part,
        name="sent_part",
    ),
    re_path(rf"^sent/(?P<id>{MESSAGE_ID})/eml/$", views.sent_eml, name="sent_eml"),
    re_path(
        rf"^sent/(?P<id>{MESSAGE_ID})/delete/$", views.sent_delete, name="sent_delete"
    ),
    path("previews/<str:group>/<str:name>/", views.preview, name="preview"),
    path(
        "previews/<str:group>/<str:name>/html/",
        views.preview_html,
        name="preview_html",
    ),
    path(
        "previews/<str:group>/<str:name>/parts/<int:n>/",
        views.preview_part,
        name="preview_part",
    ),
    path("previews/<str:group>/<str:name>/eml/", views.preview_eml, name="preview_eml"),
    path("assets/<str:name>", views.asset, name="asset"),
]
