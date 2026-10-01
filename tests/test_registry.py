from __future__ import annotations

import pytest
from django.core.exceptions import ImproperlyConfigured
from django.core.mail import EmailMessage, EmailMultiAlternatives
from django.http import HttpRequest, QueryDict

import django_mail_preview
from django_mail_preview import EmailPreview, Preview, get_previews
from django_mail_preview import registry as registry_module
from django_mail_preview.registry import RESERVED, registry
from tests import previews
from tests.helpers import LATE_PREVIEWS

SAMPLE_IDS = ["tests.greeting", "tests.html", "tests.plain"]


def message(subject="Subject"):
    return EmailMessage(subject, "Body", "noreply@example.com", ["ada@example.com"])


def ids():
    return [preview.id for preview in get_previews()]


def find(id):
    (preview,) = [preview for preview in get_previews() if preview.id == id]
    return preview


@pytest.mark.parametrize("name", ["EmailPreview", "Preview", "get_previews"])
def test_public_api(name):
    assert name in django_mail_preview.__all__
    assert getattr(django_mail_preview, name) is getattr(registry_module, name)


def test_samples_are_discovered_through_the_tests_app():
    found = get_previews()

    assert [preview.id for preview in found] == SAMPLE_IDS
    assert {preview.group for preview in found} == {"tests"}
    assert {preview.cls for preview in found} == {previews.Samples}
    assert [preview.method for preview in found] == ["greeting", "html", "plain"]


def test_get_previews_is_repeatable():
    first = get_previews()

    second = get_previews()

    assert second == first


@pytest.mark.parametrize("id", SAMPLE_IDS)
def test_sample_renders(id):
    rendered = find(id).render()

    assert isinstance(rendered, EmailMessage)
    assert rendered.message().get_all("To") == ["ada@example.com"]


def test_html_sample_has_inline_image_and_attachment():
    rendered = find("tests.html").render()

    assert isinstance(rendered, EmailMultiAlternatives)
    assert len(rendered.alternatives) == 1
    assert len(rendered.attachments) == 2


def test_description_is_the_first_docstring_paragraph():
    descriptions = {preview.id: preview.description for preview in get_previews()}

    assert descriptions == {
        "tests.plain": "",
        "tests.html": "A welcome with an inline logo and an attachment.",
        "tests.greeting": "Greets in the language of ``?lang=``, English unless given.",
    }


def test_params_come_from_the_request(rf):
    preview = find("tests.greeting")

    rendered = preview.render(rf.get("/", {"lang": "de"}))

    assert rendered.subject == "Hallo Ada"


def test_params_are_empty_without_a_request():
    rendered = find("tests.greeting").render()

    assert rendered.subject == "Hello Ada"


def test_render_passes_the_request(rf):
    request: HttpRequest = rf.get("/", {"lang": "de"})
    seen: dict[str, object] = {}

    class Capture(EmailPreview):
        def welcome(self):
            seen["request"] = self.request
            seen["params"] = self.params
            return message()

    find("tests.welcome").render(request)

    assert seen["request"] is request
    assert seen["params"] is request.GET


def test_instance_without_a_request():
    class Bare(EmailPreview):
        pass

    instance = Bare()

    assert instance.request is None
    assert isinstance(instance.params, QueryDict)
    assert instance.params == {}


@pytest.mark.parametrize("value", [None, "Hello", {"subject": "Hello"}])
def test_render_rejects_anything_but_a_message(value):
    class Broken(EmailPreview):
        def welcome(self):
            return value

    preview = find("tests.welcome")

    with pytest.raises(TypeError) as info:
        preview.render()
    assert str(info.value) == (
        f"tests.test_registry.{Broken.__qualname__}.welcome() must return an EmailMessage, not {type(value).__name__}."
    )


def test_group_defaults_to_the_app_label():
    class Inline(EmailPreview):
        def welcome(self): ...

    groups = {preview.id: preview.group for preview in get_previews()}

    assert groups["tests.welcome"] == "tests"
    assert groups["tests.plain"] == "tests"


def test_group_outside_an_app_is_the_first_module_segment():
    class Outside(EmailPreview):
        __module__ = "scratch.previews"

        def welcome(self): ...

    preview = find("scratch.welcome")

    assert preview.group == "scratch"
    assert preview.cls is Outside


def test_group_attribute_overrides_the_app_label():
    class Custom(EmailPreview):
        group = "custom"

        def welcome(self): ...

    preview = find("custom.welcome")

    assert preview.group == "custom"
    assert preview.cls is Custom


def test_only_public_functions_are_previews():
    class Mixed(EmailPreview):
        label = "not a function"

        def welcome(self): ...

        def _helper(self): ...

        @staticmethod
        def static(): ...

        @classmethod
        def on_class(cls): ...

        @property
        def prop(self): ...

        class Nested:
            def nested(self): ...

    found = [preview.method for preview in get_previews() if preview.cls is Mixed]

    assert found == ["welcome"]


def test_inherited_methods_belong_to_the_base_class():
    class Base(EmailPreview):
        group = "base"

        def shared(self): ...

    class Child(Base):
        group = "child"

        def own(self): ...

    found = [(p.id, p.cls) for p in get_previews() if p.cls in (Base, Child)]

    assert found == [("base.shared", Base), ("child.own", Child)]


def test_redefined_class_replaces_the_entry():
    def define(subject):
        class Redefined(EmailPreview):
            def welcome(self):
                return message(subject)

        return Redefined

    first = define("first")
    second = define("second")

    assert first.__qualname__ == second.__qualname__
    assert registry["tests.test_registry", first.__qualname__] is second
    assert find("tests.welcome").cls is second
    assert find("tests.welcome").render().subject == "second"


def test_duplicate_id_names_both_classes():
    class One(EmailPreview):
        group = "shop"

        def order(self): ...

    class Two(EmailPreview):
        group = "shop"

        def order(self): ...

    with pytest.raises(ImproperlyConfigured) as info:
        get_previews()
    assert str(info.value) == (
        "Preview id 'shop.order' is used by both "
        f"tests.test_registry.{One.__qualname__} and tests.test_registry.{Two.__qualname__}. "
        "Set a different group on one of them."
    )


def test_reserved_names_are_tested():
    assert sorted(RESERVED) == ["group", "params", "render", "request"]


@pytest.mark.parametrize("name", sorted(RESERVED))
def test_reserved_name_raises(name):
    def method(self): ...

    type("Reserved", (EmailPreview,), {"__module__": __name__, name: method})

    with pytest.raises(ImproperlyConfigured) as info:
        get_previews()
    assert str(info.value) == (
        f"tests.test_registry.Reserved.{name}() can't be a preview: {name!r} is reserved. Rename the method."
    )


def test_previews_are_sorted_by_id():
    class Zulu(EmailPreview):
        group = "zulu"

        def beta(self): ...

        def alpha(self): ...

    class Alpha(EmailPreview):
        group = "alpha"

        def zulu(self): ...

    found = ids()

    assert found == sorted(found)
    assert found[0] == "alpha.zulu"
    assert found[-2:] == ["zulu.alpha", "zulu.beta"]


def test_previews_module_created_later_is_found(late_app):
    assert "lateapp.welcome" not in ids()

    (late_app / "previews.py").write_text(LATE_PREVIEWS)

    assert "lateapp.welcome" in ids()
    assert find("lateapp.welcome").render().subject == "Late"


def test_error_in_a_previews_module_propagates(late_app):
    (late_app / "previews.py").write_text("raise RuntimeError('broken previews')\n")

    with pytest.raises(RuntimeError, match="broken previews"):
        get_previews()


def test_preview_is_frozen():
    preview = find("tests.plain")

    assert isinstance(preview, Preview)
    with pytest.raises(AttributeError):
        preview.id = "other"  # type: ignore[misc]
