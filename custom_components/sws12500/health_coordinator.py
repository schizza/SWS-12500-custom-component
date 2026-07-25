"""Health and diagnostics coordinator for the SWS12500 integration.

This module owns the integration's runtime health model. The intent is to keep
all support/debug state in one place so it can be surfaced consistently via:

- diagnostic entities (`health_sensor.py`)
- diagnostics download (`diagnostics.py`)
- the `/station/health` HTTP endpoint

The coordinator is intentionally separate from the weather data coordinator.
Weather payload handling is push-based, while health metadata is lightweight
polling plus event-driven updates (route dispatch, ingress result, forwarding).
"""

from __future__ import annotations

from asyncio import timeout
from copy import deepcopy
from datetime import timedelta
import logging
from typing import Any, Final

import aiohttp
import aiohttp.web
from aiohttp.web_exceptions import HTTPUnauthorized
from py_typecheck import checked, checked_or

from homeassistant.components.http import KEY_AUTHENTICATED
from homeassistant.components.network import async_get_source_ip
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.network import NoURLAvailableError, get_url
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .const import (
    DEFAULT_URL,
    DOMAIN,
    ECOWITT_ENABLED,
    ECOWITT_URL_PREFIX,
    HEALTH_URL,
    LEGACY_ENABLED,
    POCASI_CZ_ENABLED,
    WINDY_ENABLED,
    WSLINK,
    WSLINK_ADDON_PORT,
    WSLINK_URL,
)
from .data import SWSConfigEntry
from .pocasti_cz import PocasiPush
from .routes import Routes
from .windy_func import WindyPush

_LOGGER = logging.getLogger(__name__)


# Protocols that represent a real, accepted ingress (not health / unknown).
_REAL_PROTOCOLS: frozenset[str] = frozenset({"wu", "wslink", "ecowitt"})
_LEGACY_PROTOCOLS: frozenset[str] = frozenset({"wu", "wslink"})

# Expected ways the optional add-on probe can fail. All of them simply mean
# "add-on not reachable" and are logged at debug level (see `_async_update_data`).
#   - TimeoutError      : `asyncio.timeout` expiry, e.g. a firewall dropping packets
#   - aiohttp.ClientError: connection refused, TLS failures, bad response, ...
#   - OSError           : raw socket errors not wrapped by aiohttp
#   - NoURLAvailableError: HA cannot resolve its own URL
_PROBE_ERRORS: Final = (TimeoutError, aiohttp.ClientError, OSError, NoURLAvailableError)


def _configured_protocol(config: SWSConfigEntry) -> str:
    """Return the primary configured protocol (wu / wslink / ecowitt).

    The legacy PWS/WSLink endpoint takes precedence when enabled; otherwise an
    Ecowitt-only setup reports "ecowitt". (Legacy and Ecowitt can be enabled at the
    same time; this just labels the primary protocol for the summary.)
    """
    if checked_or(config.options.get(LEGACY_ENABLED), bool, True):
        return "wslink" if checked_or(config.options.get(WSLINK), bool, False) else "wu"
    if checked_or(config.options.get(ECOWITT_ENABLED), bool, False):
        return "ecowitt"
    return "wu"


def _protocol_from_path(path: str) -> str:
    """Infer an ingress protocol label from a request path."""
    if path == WSLINK_URL:
        return "wslink"
    if path == DEFAULT_URL:
        return "wu"
    if path == HEALTH_URL:
        return "health"
    if path.startswith(ECOWITT_URL_PREFIX + "/"):
        return "ecowitt"
    return "unknown"


def _sanitize_path(path: str) -> str:
    """Strip the secret Ecowitt webhook id from a path before storing/exposing it.

    The Ecowitt endpoint is `/weatherhub/<webhook_id>` where the id is the only
    credential. Keeping the raw path in the health snapshot would leak it via the
    health endpoint and diagnostics, so mask the id segment.
    """
    if path.startswith(ECOWITT_URL_PREFIX + "/"):
        return ECOWITT_URL_PREFIX + "/***"
    return path


# Fields under "addon" that reveal internal network topology. They must not be
# exposed via entity attributes (readable by any HA user, incl. non-admins).
_SENSITIVE_ADDON_FIELDS: frozenset[str] = frozenset(
    {"health_url", "info_url", "home_assistant_url", "home_assistant_source_ip", "raw_status"}
)


def public_health_snapshot(data: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of the health snapshot safe to expose to any HA user.

    Removes internal network details (HA source IP, internal URLs, raw add-on
    status). The full snapshot stays available only via the authenticated
    `/station/health` endpoint and the admin-only (redacted) diagnostics download.
    """
    public: dict[str, Any] = deepcopy(data)
    addon = checked(public.get("addon"), dict[str, Any])
    if addon is not None:
        for field in _SENSITIVE_ADDON_FIELDS:
            addon.pop(field, None)
    return public


def _empty_forwarding_state(enabled: bool) -> dict[str, Any]:
    """Build the default forwarding status payload."""
    return {
        "enabled": enabled,
        "last_status": "disabled" if not enabled else "idle",
        "last_error": None,
        "last_attempt_at": None,
    }


def _default_health_data(config: SWSConfigEntry) -> dict[str, Any]:
    """Build the default health/debug payload for this config entry."""
    configured_protocol = _configured_protocol(config)
    return {
        "integration_status": f"online_{configured_protocol}",
        "configured_protocol": configured_protocol,
        "active_protocol": configured_protocol,
        "addon": {
            "online": False,
            "health_endpoint": "/healthz",
            "info_endpoint": "/status/internal",
            "name": None,
            "version": None,
            "listen_port": None,
            "tls": None,
            "upstream_ha_port": None,
            "paths": {
                "wslink": WSLINK_URL,
                "wu": DEFAULT_URL,
            },
            "raw_status": None,
        },
        "routes": {
            "wu_enabled": False,
            "wslink_enabled": False,
            "health_enabled": False,
            "snapshot": {},
        },
        "last_ingress": {
            "time": None,
            "protocol": "unknown",
            "path": None,
            "method": None,
            "route_enabled": False,
            "accepted": False,
            "authorized": None,
            "reason": "no_data",
        },
        "forwarding": {
            "windy": _empty_forwarding_state(checked_or(config.options.get(WINDY_ENABLED), bool, False)),
            "pocasi": _empty_forwarding_state(checked_or(config.options.get(POCASI_CZ_ENABLED), bool, False)),
        },
    }


class HealthCoordinator(DataUpdateCoordinator):
    """Maintain the integration health snapshot.

    The coordinator combines:
    - periodic add-on reachability checks
    - live ingress observations from the HTTP dispatcher
    - ingress processing results from the main webhook handler
    - forwarding status from Windy/Pocasi helpers

    All of that is stored as one structured JSON-like dict in `self.data`.
    """

    def __init__(self, hass: HomeAssistant, config: SWSConfigEntry) -> None:
        """Initialize the health coordinator."""
        self.hass: HomeAssistant = hass
        self.config: SWSConfigEntry = config

        super().__init__(
            hass,
            logger=_LOGGER,
            config_entry=config,
            name=f"{DOMAIN}_health",
            update_interval=timedelta(minutes=1),
        )

        self.data: dict[str, Any] = _default_health_data(config)

    def _store_runtime_health(self, data: dict[str, Any]) -> None:
        """Persist the latest health payload into entry runtime storage."""

        try:
            self.config.runtime_data.health_data = deepcopy(data)
        except AttributeError:
            # runtime_data may not be set up yet during early initialization; that's fine, we'll populate it on the next tick.
            return

    def _commit(self, data: dict[str, Any]) -> dict[str, Any]:
        """Publish a new health snapshot."""
        self.async_set_updated_data(data)
        self._store_runtime_health(data)
        return data

    def _refresh_summary(self, data: dict[str, Any]) -> None:
        """Derive top-level integration status from the detailed health payload."""

        configured_protocol = data.get("configured_protocol", "wu")
        ingress = data.get("last_ingress", {})
        last_protocol = ingress.get("protocol", "unknown")
        accepted = bool(ingress.get("accepted"))
        reason = ingress.get("reason")

        # A WU vs WSLink mismatch means the station is misconfigured for the legacy
        # endpoint. Ecowitt coexists with the legacy endpoint, so it never counts as a
        # mismatch - it is a valid protocol whenever a payload arrives on its route.
        legacy_mismatch = (
            last_protocol in _LEGACY_PROTOCOLS
            and configured_protocol in _LEGACY_PROTOCOLS
            and last_protocol != configured_protocol
        )

        if (reason in {"route_disabled", "route_not_registered", "unauthorized"}) or legacy_mismatch:
            integration_status = "degraded"
        elif accepted and last_protocol in _REAL_PROTOCOLS:
            integration_status = f"online_{last_protocol}"
        else:
            integration_status = "online_idle"

        data["integration_status"] = integration_status
        data["active_protocol"] = (
            last_protocol if accepted and last_protocol in _REAL_PROTOCOLS else configured_protocol
        )

    async def _probe_addon(self, addon: dict[str, Any]) -> None:
        """Fill `addon` with live WSLink proxy metadata.

        May raise: turning a failed probe into `online: False` is the caller's job.
        Fields are written as they are resolved, so a failure part-way through still
        leaves the snapshot with everything learned up to that point.
        """
        session = async_get_clientsession(self.hass, False)

        ip = await async_get_source_ip(self.hass)
        port = checked_or(self.config.options.get(WSLINK_ADDON_PORT), int, 443)

        health_url = f"https://{ip}:{port}/healthz"
        info_url = f"https://{ip}:{port}/status/internal"

        addon["health_url"] = health_url
        addon["info_url"] = info_url
        addon["home_assistant_source_ip"] = str(ip)

        # Informational only, and independently fallible (`NoURLAvailableError`),
        # so it must not prevent the reachability probe below from running.
        try:
            addon["home_assistant_url"] = get_url(self.hass)
        except NoURLAvailableError:
            _LOGGER.debug("No Home Assistant URL available for the health snapshot")

        async with timeout(5), session.get(health_url) as response:
            addon["online"] = checked(response.status, int) == 200

        if not addon["online"]:
            return

        raw_status: dict[str, Any] | None = None
        try:
            async with timeout(5), session.get(info_url) as info_response:
                if checked(info_response.status, int) == 200:
                    # A non-dict body (or malformed JSON) is treated as "no status".
                    raw_status = checked(await info_response.json(content_type=None), dict[str, Any])
        except (*_PROBE_ERRORS, ValueError):
            raw_status = None

        addon["raw_status"] = raw_status
        if not raw_status:
            return

        listen = checked_or(raw_status.get("listen"), dict[str, Any], {})
        upstream = checked_or(raw_status.get("upstream"), dict[str, Any], {})
        paths = checked_or(raw_status.get("paths"), dict[str, Any], {})

        addon["name"] = raw_status.get("addon")
        addon["version"] = raw_status.get("version")
        addon["listen_port"] = listen.get("port")
        addon["tls"] = listen.get("tls")
        addon["upstream_ha_port"] = upstream.get("ha_port")
        addon["paths"] = {
            "wslink": paths.get("wslink", WSLINK_URL),
            "wu": paths.get("wu", DEFAULT_URL),
        }

    async def _async_update_data(self) -> dict[str, Any]:
        """Refresh add-on health metadata from the WSLink proxy.

        The proxy add-on can front any protocol (WU / WSLink / Ecowitt), so the probe
        is not gated on a specific protocol option - it always runs.

        The add-on is *optional* and this coordinator only produces diagnostics, so the
        probe must never fail the update. `async_config_entry_first_refresh` turns any
        exception raised here into `ConfigEntryNotReady`, which would take the station
        webhook - the actual job of this integration - down with it. An unreachable or
        misbehaving add-on is therefore recorded as `online: False`, never raised.
        """
        data = deepcopy(self.data)
        addon = data["addon"]
        addon["online"] = False
        addon["raw_status"] = None

        try:
            await self._probe_addon(addon)
        except _PROBE_ERRORS as err:
            _LOGGER.debug("WSLink add-on probe failed (%s): %s", type(err).__name__, err)
            addon["online"] = False
        except Exception:  # noqa: BLE001 - diagnostics must never fail the config entry
            _LOGGER.exception("Unexpected error while probing the WSLink add-on")
            addon["online"] = False

        self._refresh_summary(data)
        return self._commit(data)

    def update_routing(self, routes: Routes | None) -> None:
        """Store the currently enabled routes for diagnostics."""
        data = deepcopy(self.data)
        data["configured_protocol"] = _configured_protocol(self.config)
        if routes is not None:
            data["routes"] = {
                "wu_enabled": routes.path_enabled(DEFAULT_URL),
                "wslink_enabled": routes.path_enabled(WSLINK_URL),
                "health_enabled": routes.path_enabled(HEALTH_URL),
                "snapshot": routes.snapshot(),
            }
        self._refresh_summary(data)
        self._commit(data)

    def record_dispatch(self, request: aiohttp.web.Request, route_enabled: bool, reason: str | None) -> None:
        """Record every ingress observed by the dispatcher.

        This runs before the actual webhook handler. It lets diagnostics answer:
        - which endpoint the station is calling
        - whether the route was enabled
        - whether the request was rejected before processing
        """

        # We do not want to process health requests
        if request.path == HEALTH_URL:
            return

        data = deepcopy(self.data)
        data["last_ingress"] = {
            "time": dt_util.utcnow().isoformat(),
            "protocol": _protocol_from_path(request.path),
            "path": _sanitize_path(request.path),
            "method": request.method,
            "route_enabled": route_enabled,
            "accepted": False,
            "authorized": None,
            "reason": reason or "pending",
        }
        self._refresh_summary(data)
        self._commit(data)

    def update_ingress_result(
        self,
        request: aiohttp.web.Request,
        *,
        accepted: bool,
        authorized: bool | None,
        reason: str | None = None,
    ) -> None:
        """Store the final processing result of a webhook request."""
        data = deepcopy(self.data)
        ingress = data.get("last_ingress", {})
        ingress.update(
            {
                "time": dt_util.utcnow().isoformat(),
                "protocol": _protocol_from_path(request.path),
                "path": _sanitize_path(request.path),
                "method": request.method,
                "accepted": accepted,
                "authorized": authorized,
                "reason": reason or ("accepted" if accepted else "rejected"),
            }
        )
        data["last_ingress"] = ingress
        self._refresh_summary(data)
        self._commit(data)

    def update_forwarding(self, windy: WindyPush, pocasi: PocasiPush) -> None:
        """Store forwarding subsystem statuses for diagnostics."""
        data = deepcopy(self.data)

        data["forwarding"] = {
            "windy": {
                "enabled": windy.enabled,
                "last_status": windy.last_status,
                "last_error": windy.last_error,
                "last_attempt_at": windy.last_attempt_at,
            },
            "pocasi": {
                "enabled": pocasi.enabled,
                "last_status": pocasi.last_status,
                "last_error": pocasi.last_error,
                "last_attempt_at": pocasi.last_attempt_at,
            },
        }
        self._refresh_summary(data)
        self._commit(data)

    async def health_status(self, request: aiohttp.web.Request) -> aiohttp.web.Response:
        """Serve the current health snapshot over HTTP.

        Requires Home Assistant authentication. The route is registered directly on
        the aiohttp router (so it can share the dispatcher), which means HA's auth
        middleware only *flags* the request - it does not block it. We therefore
        enforce auth here so the snapshot (internal URLs/IPs, add-on status, last
        ingress) is never exposed to unauthenticated callers.

        Auth is satisfied by a valid bearer token or a signed request, the same as
        any HomeAssistantView.

        The endpoint forces one refresh before returning so that the caller sees
        a reasonably fresh add-on status.
        """
        if not request.get(KEY_AUTHENTICATED, False):
            raise HTTPUnauthorized

        await self.async_request_refresh()
        return aiohttp.web.json_response(self.data, status=200)
