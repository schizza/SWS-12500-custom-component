from __future__ import annotations

from dataclasses import dataclass
from typing import Awaitable, Callable

from aiohttp.web import Response
import pytest

from custom_components.sws12500.routes import Routes, unregistered

Handler = Callable[["_RequestStub"], Awaitable[Response]]


@dataclass(slots=True)
class _RequestStub:
    """Minimal request stub for unit-testing the dispatcher.

    `Routes.dispatch` relies on `request.path`.
    `unregistered` accepts a request object but does not use it.
    """

    path: str


@pytest.fixture
def routes() -> Routes:
    return Routes()


async def test_dispatch_unknown_path_calls_unregistered(routes: Routes) -> None:
    request = _RequestStub(path="/unregistered")
    response = await routes.dispatch(request)  # type: ignore[arg-type]
    assert response.status == 400


async def test_unregistered_handler_returns_400() -> None:
    request = _RequestStub(path="/invalid")
    response = await unregistered(request)  # type: ignore[arg-type]
    assert response.status == 400


async def test_dispatch_registered_but_disabled_uses_fallback(routes: Routes) -> None:
    async def handler(_request: _RequestStub) -> Response:
        return Response(text="OK", status=200)

    routes.add_route("/a", handler, enabled=False)

    response = await routes.dispatch(_RequestStub(path="/a"))  # type: ignore[arg-type]
    assert response.status == 400


async def test_dispatch_registered_and_enabled_uses_handler(routes: Routes) -> None:
    async def handler(_request: _RequestStub) -> Response:
        return Response(text="OK", status=201)

    routes.add_route("/a", handler, enabled=True)

    response = await routes.dispatch(_RequestStub(path="/a"))  # type: ignore[arg-type]
    assert response.status == 201


def test_switch_route_enables_exactly_one(routes: Routes) -> None:
    async def handler_a(_request: _RequestStub) -> Response:
        return Response(text="A", status=200)

    async def handler_b(_request: _RequestStub) -> Response:
        return Response(text="B", status=200)

    routes.add_route("/a", handler_a, enabled=True)
    routes.add_route("/b", handler_b, enabled=False)

    routes.switch_route("/b")

    assert routes.routes["/a"].enabled is False
    assert routes.routes["/b"].enabled is True


def test_show_enabled_returns_message_when_none_enabled(routes: Routes) -> None:
    async def handler(_request: _RequestStub) -> Response:
        return Response(text="OK", status=200)

    routes.add_route("/a", handler, enabled=False)
    routes.add_route("/b", handler, enabled=False)

    assert routes.show_enabled() == "No routes is enabled."


def test_show_enabled_includes_url_when_enabled(routes: Routes) -> None:
    async def handler(_request: _RequestStub) -> Response:
        return Response(text="OK", status=200)

    routes.add_route("/a", handler, enabled=False)
    routes.add_route("/b", handler, enabled=True)

    msg = routes.show_enabled()
    assert "Dispatcher enabled for URL: /b" in msg
    assert "handler" in msg
