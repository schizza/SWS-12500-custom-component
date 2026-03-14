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
from typing import Any

from aiohttp.web import AbstractRoute, Request, Response

_LOGGER = logging.getLogger(__name__)

Handler = Callable[[Request], Awaitable[Response]]
IngressObserver = Callable[[Request, bool, str | None], None]


@dataclass
class RouteInfo:
    """Route definition held by the dispatcher.

    - `handler` is the real webhook handler (bound method).
    - `fallback` is used when the route exists but is currently disabled.
    """

    url_path: str
    route: AbstractRoute
    handler: Handler
    enabled: bool = False
    sticky: bool = False

    fallback: Handler = field(default_factory=lambda: unregistered)

    def __str__(self):
        """Return string representation."""
        return f"RouteInfo(url_path={self.url_path}, route={self.route}, handler={self.handler}, enabled={self.enabled}, fallback={self.fallback})"


class Routes:
    """Simple route dispatcher.

    We register aiohttp routes once and direct traffic to the currently enabled endpoint
    using `switch_route`. This keeps route registration stable while still allowing the
    integration to support multiple incoming push formats.
    """

    def __init__(self) -> None:
        """Initialize dispatcher storage."""
        self.routes: dict[str, RouteInfo] = {}
        self._ingress_observer: IngressObserver | None = None

    def set_ingress_observer(self, observer: IngressObserver | None) -> None:
        """Set a callback notified for every incoming dispatcher request."""
        self._ingress_observer = observer

    async def dispatch(self, request: Request) -> Response:
        """Dispatch incoming request to either the enabled handler or a fallback."""
        key = f"{request.method}:{request.path}"
        info = self.routes.get(key)
        if not info:
            _LOGGER.debug(
                "Route (%s):%s is not registered!", request.method, request.path
            )
            if self._ingress_observer is not None:
                self._ingress_observer(request, False, "route_not_registered")
            return await unregistered(request)

        if self._ingress_observer is not None:
            self._ingress_observer(
                request,
                info.enabled,
                None if info.enabled else "route_disabled",
            )

        handler = info.handler if info.enabled else info.fallback
        return await handler(request)

    def switch_route(self, handler: Handler, url_path: str) -> None:
        """Enable routes based on URL, disable all others. Leave sticky routes enabled.

        This is called when options change (e.g. WSLink toggle). The aiohttp router stays
        untouched; we only flip which internal handler is active.
        """
        for route in self.routes.values():
            if route.sticky:
                continue

            if route.url_path == url_path:
                _LOGGER.info(
                    "New coordinator to route: (%s):%s",
                    route.route.method,
                    route.url_path,
                )
                route.enabled = True
                route.handler = handler
            else:
                route.enabled = False
                route.handler = unregistered

    def add_route(
        self,
        url_path: str,
        route: AbstractRoute,
        handler: Handler,
        *,
        enabled: bool = False,
        sticky: bool = False,
    ) -> None:
        """Register a route in the dispatcher.

        This does not register anything in aiohttp. It only stores routing metadata that
        `dispatch` uses after aiohttp has routed the request by path.
        """
        key = f"{route.method}:{url_path}"
        self.routes[key] = RouteInfo(
            url_path, route=route, handler=handler, enabled=enabled, sticky=sticky
        )
        _LOGGER.debug("Registered dispatcher for route (%s):%s", route.method, url_path)

    def show_enabled(self) -> str:
        """Return a human-readable description of the currently enabled route."""

        enabled_routes = {
            f"Dispatcher enabled for ({route.route.method}):{route.url_path}, with handler: {route.handler}"
            for route in self.routes.values()
            if route.enabled
        }
        if not enabled_routes:
            return "No routes are enabled."
        return ", ".join(sorted(enabled_routes))

    def path_enabled(self, url_path: str) -> bool:
        """Return whether any route registered for `url_path` is enabled."""
        return any(
            route.enabled for route in self.routes.values() if route.url_path == url_path
        )

    def snapshot(self) -> dict[str, Any]:
        """Return a compact routing snapshot for diagnostics."""
        return {
            key: {
                "path": route.url_path,
                "method": route.route.method,
                "enabled": route.enabled,
                "sticky": route.sticky,
            }
            for key, route in self.routes.items()
        }


async def unregistered(request: Request) -> Response:
    """Fallback response for unknown/disabled routes.

    This should normally never happen for correctly configured stations, but it provides
    a clear error message when the station pushes to the wrong endpoint.
    """
    _ = request
    _LOGGER.debug("Received data to unregistred or disabled webhook.")
    return Response(text="Unregistred webhook. Check your settings.", status=400)
