"""Lint-style checks for the scoping contract (P2-05).

Limitation (documented in PHASE-3-HANDOFF): views are detected through a class-level ``queryset``
attribute, the idiom this project uses; a view that builds its queryset only in ``get_queryset`` must
still use ``ScopedViewMixin`` and is covered by review.
"""

import pytest
from django.apps import apps
from django.urls import URLPattern, URLResolver, path
from rest_framework.generics import ListAPIView

from apps.accounts.querysets import ScopedQuerySet, ScopedViewMixin
from tests.testapp.models import ScopedThing
from tests.testapp.urls import unscoped_patterns, urlpatterns
from tests.testapp.views import ThingSerializer


def scoped_models():
    return [m for m in apps.get_models() if isinstance(m._default_manager.get_queryset(), ScopedQuerySet)]


def view_classes(patterns):
    for entry in patterns:
        if isinstance(entry, URLResolver):
            yield from view_classes(entry.url_patterns)
        elif isinstance(entry, URLPattern):
            yield str(entry.pattern), getattr(entry.callback, "cls", None)


def find_unscoped_views(patterns) -> list[str]:
    problems = []
    for route, cls in view_classes(patterns):
        serves_scoped_rows = cls is not None and isinstance(getattr(cls, "queryset", None), ScopedQuerySet)
        if serves_scoped_rows and not issubclass(cls, ScopedViewMixin):
            problems.append(f"{route}: {cls.__name__} serves a scoped model without ScopedViewMixin")
    return problems


def test_scoped_models_are_discovered():
    assert ScopedThing in scoped_models()  # guards against a vacuous pass


@pytest.mark.parametrize("model", scoped_models(), ids=lambda m: m.__name__)
def test_scoped_models_implement_for_user_and_scope_to_user(model):
    queryset_class = type(model._default_manager.get_queryset())
    assert queryset_class.scope_to_user is not ScopedQuerySet.scope_to_user
    assert callable(getattr(model._default_manager, "for_user", None))


def test_views_over_scoped_models_use_the_scoped_mixin():
    assert find_unscoped_views(urlpatterns) == []


def test_lint_detects_a_view_that_bypasses_scoping():
    class Leaky(ListAPIView):
        queryset = ScopedThing.objects.all()
        serializer_class = ThingSerializer

    problems = find_unscoped_views([path("leaky/", Leaky.as_view()), *unscoped_patterns])
    assert len(problems) == 2 and all("without ScopedViewMixin" in p for p in problems)
