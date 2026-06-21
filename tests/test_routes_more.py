"""Additional Routes coverage: __str__, ingress observer calls, canonical fallback."""

from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from unittest.mock import MagicMock

from aiohttp.web import Response
import pytest

from custom_components.sws12500.routes import RouteInfo, Routes


@dataclass(slots=True)
class _RouteStub:
    method: str


@dataclass(slots=True)
class _RequestStub:
    method: str
    path: str


@pytest.fixture
def routes() -> Routes:
    return Routes()


async def _handler(_request) -> Response:
    return Response(text="OK", status=200)


def test_routeinfo_str_contains_fields() -> None:
    info = RouteInfo("/a", route=_RouteStub(method="GET"), handler=_handler, enabled=True)
    text = str(info)
    assert "RouteInfo(" in text
    assert "url_path=/a" in text
    assert "enabled=True" in text


async def test_dispatch_unknown_path_notifies_observer(routes: Routes) -> None:
    observer = MagicMock()
    routes.set_ingress_observer(observer)

    await routes.dispatch(_RequestStub(method="GET", path="/nope"))  # type: ignore[arg-type]

    observer.assert_called_once()
    args = observer.call_args.args
    assert args[1] is False
    assert args[2] == "route_not_registered"


async def test_dispatch_known_path_notifies_observer(routes: Routes) -> None:
    routes.add_route("/a", _RouteStub(method="GET"), _handler, enabled=True)
    observer = MagicMock()
    routes.set_ingress_observer(observer)

    resp = await routes.dispatch(_RequestStub(method="GET", path="/a"))  # type: ignore[arg-type]
    assert resp.status == 200

    observer.assert_called_once()
    args = observer.call_args.args
    assert args[1] is True
    assert args[2] is None


async def test_dispatch_resolves_via_canonical_resource(routes: Routes) -> None:
    """A path with a parameter resolves through the aiohttp resource canonical URL."""
    canonical = "/weatherhub/{webhook_id}"
    routes.add_route(canonical, _RouteStub(method="POST"), _handler, enabled=True)

    # Direct key "POST:/weatherhub/abc" is absent; fall back to resource.canonical.
    request = SimpleNamespace(
        method="POST",
        path="/weatherhub/abc",
        match_info=SimpleNamespace(route=SimpleNamespace(resource=SimpleNamespace(canonical=canonical))),
    )

    resp = await routes.dispatch(request)  # type: ignore[arg-type]
    assert resp.status == 200
