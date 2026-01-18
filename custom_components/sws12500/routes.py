"""Routes implementation."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
import logging

from aiohttp.web import Request, Response

_LOGGER = logging.getLogger(__name__)

Handler = Callable[[Request], Awaitable[Response]]


@dataclass
class RouteInfo:
    """Route struct."""

    url_path: str
    handler: Handler
    enabled: bool = False
    fallback: Handler = field(default_factory=lambda: unregistred)


class Routes:
    """Routes class."""

    def __init__(self) -> None:
        """Init."""
        self.routes: dict[str, RouteInfo] = {}

    async def dispatch(self, request: Request) -> Response:
        """Dispatch."""
        info = self.routes.get(request.path)
        if not info:
            _LOGGER.debug("Route %s is not registered!", request.path)
            return await unregistred(request)
        handler = info.handler if info.enabled else info.fallback
        return await handler(request)

    def switch_route(self, url_path: str) -> None:
        """Switch route to new handler."""
        for path, info in self.routes.items():
            info.enabled = path == url_path

    def add_route(
        self, url_path: str, handler: Handler, *, enabled: bool = False
    ) -> None:
        """Add route to dispatcher."""

        self.routes[url_path] = RouteInfo(url_path, handler, enabled=enabled)
        _LOGGER.debug("Registered dispatcher for route %s", url_path)

    def show_enabled(self) -> str:
        """Show info of enabled route."""
        for url, route in self.routes.items():
            if route.enabled:
                return (
                    f"Dispatcher enabled for URL: {url}, with handler: {route.handler}"
                )
        return "No routes is enabled."


async def unregistred(request: Request) -> Response:
    """Return unregistred error."""
    _ = request
    _LOGGER.debug("Received data to unregistred or disabled webhook.")
    return Response(text="Unregistred webhook. Check your settings.", status=400)
