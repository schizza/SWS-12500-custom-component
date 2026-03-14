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
from typing import Any

import aiohttp
from aiohttp import ClientConnectionError
import aiohttp.web
from py_typecheck import checked, checked_or

from homeassistant.components.network import async_get_source_ip
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.network import get_url
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .const import (
    DEFAULT_URL,
    DOMAIN,
    HEALTH_URL,
    POCASI_CZ_ENABLED,
    WINDY_ENABLED,
    WSLINK,
    WSLINK_URL,
)
from .data import ENTRY_HEALTH_DATA
from .pocasti_cz import PocasiPush
from .routes import Routes
from .windy_func import WindyPush

_LOGGER = logging.getLogger(__name__)


def _protocol_name(wslink_enabled: bool) -> str:
    """Return the configured protocol name."""
    return "wslink" if wslink_enabled else "wu"


def _protocol_from_path(path: str) -> str:
    """Infer an ingress protocol label from a request path."""
    if path == WSLINK_URL:
        return "wslink"
    if path == DEFAULT_URL:
        return "wu"
    if path == HEALTH_URL:
        return "health"
    return "unknown"


def _empty_forwarding_state(enabled: bool) -> dict[str, Any]:
    """Build the default forwarding status payload."""
    return {
        "enabled": enabled,
        "last_status": "disabled" if not enabled else "idle",
        "last_error": None,
        "last_attempt_at": None,
    }


def _default_health_data(config: ConfigEntry) -> dict[str, Any]:
    """Build the default health/debug payload for this config entry."""
    configured_protocol = _protocol_name(
        checked_or(config.options.get(WSLINK), bool, False)
    )
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
            "windy": _empty_forwarding_state(
                checked_or(config.options.get(WINDY_ENABLED), bool, False)
            ),
            "pocasi": _empty_forwarding_state(
                checked_or(config.options.get(POCASI_CZ_ENABLED), bool, False)
            ),
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

    def __init__(self, hass: HomeAssistant, config: ConfigEntry) -> None:
        """Initialize the health coordinator."""
        self.hass: HomeAssistant = hass
        self.config: ConfigEntry = config

        super().__init__(
            hass,
            logger=_LOGGER,
            name=f"{DOMAIN}_health",
            update_interval=timedelta(minutes=1),
        )

        self.data: dict[str, Any] = _default_health_data(config)

    def _store_runtime_health(self, data: dict[str, Any]) -> None:
        """Persist the latest health payload into entry runtime storage."""

        if (domain := checked(self.hass.data.get(DOMAIN), dict[str, Any])) is None:
            return

        if (entry := checked(domain.get(self.config.entry_id), dict[str, Any])) is None:
            return

        entry[ENTRY_HEALTH_DATA] = deepcopy(data)

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

        if (reason in {"route_disabled", "route_not_registered", "unauthorized"}) or (
            last_protocol in {"wu", "wslink"} and last_protocol != configured_protocol
        ):
            integration_status = "degraded"
        elif accepted and last_protocol in {"wu", "wslink"}:
            integration_status = f"online_{last_protocol}"
        else:
            integration_status = "online_idle"

        data["integration_status"] = integration_status
        data["active_protocol"] = (
            last_protocol
            if accepted and last_protocol in {"wu", "wslink"}
            else configured_protocol
        )

    async def _async_update_data(self) -> dict[str, Any]:
        """Refresh add-on health metadata from the WSLink proxy."""
        session = async_get_clientsession(self.hass, False)
        url = get_url(self.hass)
        ip = await async_get_source_ip(self.hass)

        health_url = f"https://{ip}/healthz"
        info_url = f"https://{ip}/status/internal"

        data = deepcopy(self.data)
        addon = data["addon"]
        addon["health_url"] = health_url
        addon["info_url"] = info_url
        addon["home_assistant_url"] = url
        addon["home_assistant_source_ip"] = str(ip)
        addon["online"] = False

        try:
            async with timeout(5), session.get(health_url) as response:
                addon["online"] = checked(response.status, int) == 200
        except ClientConnectionError:
            addon["online"] = False

        raw_status: dict[str, Any] | None = None
        if addon["online"]:
            try:
                async with timeout(5), session.get(info_url) as info_response:
                    if checked(info_response.status, int) == 200:
                        raw_status = await info_response.json(content_type=None)
            except (ClientConnectionError, aiohttp.ContentTypeError, ValueError):
                raw_status = None

        addon["raw_status"] = raw_status
        if raw_status:
            addon["name"] = raw_status.get("addon")
            addon["version"] = raw_status.get("version")
            addon["listen_port"] = raw_status.get("listen", {}).get("port")
            addon["tls"] = raw_status.get("listen", {}).get("tls")
            addon["upstream_ha_port"] = raw_status.get("upstream", {}).get("ha_port")
            addon["paths"] = {
                "wslink": raw_status.get("paths", {}).get("wslink", WSLINK_URL),
                "wu": raw_status.get("paths", {}).get("wu", DEFAULT_URL),
            }

        self._refresh_summary(data)
        return self._commit(data)

    def update_routing(self, routes: Routes | None) -> None:
        """Store the currently enabled routes for diagnostics."""
        data = deepcopy(self.data)
        data["configured_protocol"] = _protocol_name(
            checked_or(self.config.options.get(WSLINK), bool, False)
        )
        if routes is not None:
            data["routes"] = {
                "wu_enabled": routes.path_enabled(DEFAULT_URL),
                "wslink_enabled": routes.path_enabled(WSLINK_URL),
                "health_enabled": routes.path_enabled(HEALTH_URL),
                "snapshot": routes.snapshot(),
            }
        self._refresh_summary(data)
        self._commit(data)

    def record_dispatch(
        self, request: aiohttp.web.Request, route_enabled: bool, reason: str | None
    ) -> None:
        """Record every ingress observed by the dispatcher.

        This runs before the actual webhook handler. It lets diagnostics answer:
        - which endpoint the station is calling
        - whether the route was enabled
        - whether the request was rejected before processing
        """

        # We do not want to proccess health requests
        if request.path == HEALTH_URL:
            return

        data = deepcopy(self.data)
        data["last_ingress"] = {
            "time": dt_util.utcnow().isoformat(),
            "protocol": _protocol_from_path(request.path),
            "path": request.path,
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
                "path": request.path,
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

    async def health_status(self, _: aiohttp.web.Request) -> aiohttp.web.Response:
        """Serve the current health snapshot over HTTP.

        The endpoint forces one refresh before returning so that the caller sees
        a reasonably fresh add-on status.
        """
        await self.async_request_refresh()
        return aiohttp.web.json_response(self.data, status=200)
