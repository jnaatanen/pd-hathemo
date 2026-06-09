"""Async client for the Themo Public API v2.1."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime
import logging
from typing import Any

import httpx

from .const import API_VERSION, BASE_URL, REQUEST_TIMEOUT

_LOGGER = logging.getLogger(__name__)


class ThemoError(Exception):
    """Base error for the Themo client."""


class ThemoAuthError(ThemoError):
    """Raised when authentication fails."""


class ThemoConnectionError(ThemoError):
    """Raised on network/HTTP failures."""


@dataclass
class DeviceState:
    """Parsed device state (DeviceStateDto)."""

    info: float | None
    room_temperature: float | None
    floor_temperature: float | None
    outside_temperature: float | None
    manual_temperature: float | None
    mode: str | None
    load_state: int | None
    max_power: float | None
    lights: int | None
    is_air: bool
    is_floor: bool
    is_combi: bool
    is_price_switch: bool

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "DeviceState":
        params = data.get("DeviceParameters") or {}
        return cls(
            info=data.get("Info"),
            room_temperature=data.get("RT"),
            floor_temperature=data.get("FloorT"),
            outside_temperature=data.get("OT"),
            manual_temperature=data.get("MT"),
            mode=data.get("Mode"),
            load_state=data.get("LS"),
            max_power=data.get("MP"),
            lights=data.get("Lights"),
            is_air=bool(params.get("IsAir")),
            is_floor=bool(params.get("IsFloor")),
            is_combi=bool(params.get("IsCombi")),
            is_price_switch=bool(params.get("IsPriceSwitch")),
        )


@dataclass
class ThemoDevice:
    """A Themo device with its latest state."""

    id: int
    environment_id: int
    name: str
    serial: str
    sw_version: str | None
    model: str
    state: DeviceState | None

    @classmethod
    def from_json(cls, env_id: int, data: dict[str, Any]) -> "ThemoDevice":
        raw_state = data.get("State")
        return cls(
            id=int(data["Id"]),
            environment_id=int(data.get("EnvironmentId", env_id)),
            name=data.get("Name") or f"Themo {data['Id']}",
            serial=data.get("DeviceId") or str(data["Id"]),
            sw_version=data.get("SW"),
            model=_parse_model(data.get("Tags")),
            state=DeviceState.from_json(raw_state) if raw_state else None,
        )


@dataclass
class ThemoSchedule:
    """A device schedule (list view, without setpoints)."""

    id: int
    name: str
    parameter: str
    active: bool
    unit: str | None

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "ThemoSchedule":
        return cls(
            id=int(data["Id"]),
            name=data.get("Name") or "",
            parameter=data.get("Parameter") or "",
            active=bool(data.get("Active")),
            unit=data.get("Unit"),
        )


def _parse_model(tags: str | None) -> str:
    """Pick a model token (e.g. T700) from the pipe-delimited Tags field."""
    if tags:
        for token in tags.split("|"):
            if token.startswith("T") and token[1:].isdigit():
                return token
    return "Smart Thermostat"


class ThemoApiClient:
    """Thin async client over the Themo v2.1 REST API."""

    def __init__(
        self, username: str, password: str, http_client: httpx.AsyncClient
    ) -> None:
        self._username = username
        self._password = password
        self._http = http_client
        self._token: str | None = None
        self._auth_lock = asyncio.Lock()

    @property
    def token(self) -> str | None:
        return self._token

    async def authenticate(self) -> None:
        """Log in and store a bearer token."""
        async with self._auth_lock:
            await self._login()

    async def _login(self) -> None:
        try:
            resp = await self._http.post(
                f"{BASE_URL}/api/auth/login",
                params={"api-version": API_VERSION},
                json={"Username": self._username, "Password": self._password},
                timeout=REQUEST_TIMEOUT,
            )
        except httpx.HTTPError as err:
            raise ThemoConnectionError(f"Login request failed: {err}") from err
        if resp.status_code in (400, 401):
            raise ThemoAuthError("Invalid Themo credentials")
        try:
            resp.raise_for_status()
        except httpx.HTTPStatusError as err:
            raise ThemoConnectionError(f"Login failed: {err}") from err
        token = (resp.json() or {}).get("Token")
        if not token:
            raise ThemoAuthError("No token in login response")
        self._token = token

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
        allow_reauth: bool = True,
    ) -> Any:
        full_params = dict(params or {})
        full_params["api-version"] = API_VERSION
        headers = {"Authorization": f"Bearer {self._token}"} if self._token else {}
        try:
            resp = await self._http.request(
                method,
                f"{BASE_URL}/{path}",
                params=full_params,
                json=json,
                headers=headers,
                timeout=REQUEST_TIMEOUT,
            )
        except httpx.HTTPError as err:
            raise ThemoConnectionError(f"Request to {path} failed: {err}") from err

        if resp.status_code == 401 and allow_reauth:
            async with self._auth_lock:
                await self._login()
            return await self._request(
                method, path, params=params, json=json, allow_reauth=False
            )
        if resp.status_code == 401:
            raise ThemoAuthError("Unauthorized")
        try:
            resp.raise_for_status()
        except httpx.HTTPStatusError as err:
            raise ThemoConnectionError(f"Request to {path} failed: {err}") from err
        if not resp.content:
            return None
        return resp.json()

    async def get_environments(self) -> list[dict[str, Any]]:
        return await self._request("GET", "api/environments") or []

    async def get_devices(self, environment_id: int) -> list[ThemoDevice]:
        raw = await self._request(
            "GET",
            f"api/environments/{environment_id}/devices",
            params={"state": "true"},
        )
        return [ThemoDevice.from_json(environment_id, d) for d in (raw or [])]

    async def get_device_data(
        self,
        environment_id: int,
        device_id: int,
        dt_from: datetime,
        dt_to: datetime,
    ) -> list[dict[str, Any]]:
        return (
            await self._request(
                "GET",
                f"api/environments/{environment_id}/devices/{device_id}/data",
                params={
                    "from": dt_from.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "to": dt_to.strftime("%Y-%m-%dT%H:%M:%SZ"),
                },
            )
            or []
        )

    async def send_command(
        self, environment_id: int, device_id: int, body: dict[str, Any]
    ) -> None:
        await self._request(
            "POST",
            f"api/environments/{environment_id}/devices/{device_id}/commands/message",
            json=body,
        )

    async def get_device_schedules(
        self, environment_id: int, device_id: int
    ) -> list[ThemoSchedule]:
        raw = await self._request(
            "GET",
            f"api/environments/{environment_id}/devices/{device_id}/schedules",
        )
        return [ThemoSchedule.from_json(s) for s in (raw or [])]

    async def get_schedule(
        self, environment_id: int, device_id: int, schedule_id: int
    ) -> dict[str, Any]:
        return (
            await self._request(
                "GET",
                f"api/environments/{environment_id}/devices/{device_id}/schedules/{schedule_id}",
            )
            or {}
        )

    async def activate_schedule(
        self, environment_id: int, device_id: int, schedule_id: int, name: str
    ) -> None:
        await self._request(
            "PUT",
            f"api/environments/{environment_id}/devices/{device_id}/schedules/{schedule_id}",
            json={"Name": name, "Active": True},
        )
