"""Store routes info."""

from dataclasses import dataclass
from logging import getLogger

from aiohttp.web import AbstractRoute, Response

_LOGGER = getLogger(__name__)


@dataclass
class Route:
    """Store route info."""

    url_path: str
    route: AbstractRoute
    handler: callable
    enabled: bool = False

    def __str__(self):
        """Return string representation."""
        return f"{self.url_path} -> {self.handler}"


class Routes:
    """Store routes info."""

    def __init__(self) -> None:
        """Initialize routes."""
        self.routes = {}

    def switch_route(self, coordinator: callable, url_path: str):
        """Switch route."""

        for url, route in self.routes.items():
            if url == url_path:
                _LOGGER.info("New coordinator to route: %s", route.url_path)
                route.enabled = True
                route.handler = coordinator
                route.route._handler = coordinator  # noqa: SLF001
            else:
                route.enabled = False
                route.handler = unregistred
                route.route._handler = unregistred  # noqa: SLF001

    def add_route(
        self,
        url_path: str,
        route: AbstractRoute,
        handler: callable,
        enabled: bool = False,
    ):
        """Add route."""
        self.routes[url_path] = Route(url_path, route, handler, enabled)

    def get_route(self, url_path: str) -> Route:
        """Get route."""
        return self.routes.get(url_path)

    def get_enabled(self) -> str:
        """Get enabled routes."""
        enabled_routes = [
            route.url_path for route in self.routes.values() if route.enabled
        ]
        return "".join(enabled_routes) if enabled_routes else "None"

    def __str__(self):
        """Return string representation."""
        return "\n".join([str(route) for route in self.routes.values()])


async def unregistred(*args, **kwargs):
    """Unregister path to handle incoming data."""

    _LOGGER.error("Recieved data to unregistred webhook. Check your settings")
    return Response(body=f"{'Unregistred webhook.'}", status=404)
