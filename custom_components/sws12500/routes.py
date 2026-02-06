"""Routes implementation.

Why this dispatcher exists
--------------------------
Home Assistant registers aiohttp routes on startup. Re-registering or removing routes at runtime
is awkward and error-prone (and can raise if routes already exist). This integration supports two
different push endpoints (legacy WU-style vs WSLink). To allow switching between them without
touching the aiohttp router, we register both routes once and use this in-process dispatcher to
decide which one is currently enabled.

Important note:
- Each route stores a *bound method* handler (e.g. `coordinator.received_data`). That means the
  route points to a specific coordinator instance. When the integration reloads, we must keep the
  same coordinator instance or update the stored handler accordingly. Otherwise requests may go to
  an old coordinator while entities listen to a new one (result: UI appears "frozen").
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
import logging

from aiohttp.web import Request, Response

_LOGGER = logging.getLogger(__name__)

Handler = Callable[[Request], Awaitable[Response]]


@dataclass
class RouteInfo:
    """Route definition held by the dispatcher.

    - `handler` is the real webhook handler (bound method).
    - `fallback` is used when the route exists but is currently disabled.
    """

    url_path: str
    handler: Handler
    enabled: bool = False
    fallback: Handler = field(default_factory=lambda: unregistered)


class Routes:
    """Simple route dispatcher.

    We register aiohttp routes once and direct traffic to the currently enabled endpoint
    using `switch_route`. This keeps route registration stable while still allowing the
    integration to support multiple incoming push formats.
    """

    def __init__(self) -> None:
        """Initialize dispatcher storage."""
        self.routes: dict[str, RouteInfo] = {}

    async def dispatch(self, request: Request) -> Response:
        """Dispatch incoming request to either the enabled handler or a fallback."""
        info = self.routes.get(request.path)
        if not info:
            _LOGGER.debug("Route %s is not registered!", request.path)
            return await unregistered(request)
        handler = info.handler if info.enabled else info.fallback
        return await handler(request)

    def switch_route(self, url_path: str) -> None:
        """Enable exactly one route and disable all others.

        This is called when options change (e.g. WSLink toggle). The aiohttp router stays
        untouched; we only flip which internal handler is active.
        """
        for path, info in self.routes.items():
            info.enabled = path == url_path

    def add_route(
        self, url_path: str, handler: Handler, *, enabled: bool = False
    ) -> None:
        """Register a route in the dispatcher.

        This does not register anything in aiohttp. It only stores routing metadata that
        `dispatch` uses after aiohttp has routed the request by path.
        """
        self.routes[url_path] = RouteInfo(url_path, handler, enabled=enabled)
        _LOGGER.debug("Registered dispatcher for route %s", url_path)

    def show_enabled(self) -> str:
        """Return a human-readable description of the currently enabled route."""
        for url, route in self.routes.items():
            if route.enabled:
                return (
                    f"Dispatcher enabled for URL: {url}, with handler: {route.handler}"
                )
        return "No routes is enabled."


async def unregistered(request: Request) -> Response:
    """Fallback response for unknown/disabled routes.

    This should normally never happen for correctly configured stations, but it provides
    a clear error message when the station pushes to the wrong endpoint.
    """
    _ = request
    _LOGGER.debug("Received data to unregistred or disabled webhook.")
    return Response(text="Unregistred webhook. Check your settings.", status=400)
