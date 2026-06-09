"""Websocket commands for the pd_hathemo integration."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.components import websocket_api
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant, callback

from .api import ThemoError
from .const import DOMAIN


@callback
def async_register_websocket_commands(hass: HomeAssistant) -> None:
    """Register pd_hathemo websocket commands."""
    websocket_api.async_register_command(hass, _ws_schedules)


@websocket_api.websocket_command(
    {
        vol.Required("type"): "pd_hathemo/schedules",
        vol.Required("device_id"): int,
    }
)
@websocket_api.async_response
async def _ws_schedules(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Return a device's schedules with their setpoint grids."""
    device_id = msg["device_id"]
    for entry in hass.config_entries.async_entries(DOMAIN):
        if entry.state is not ConfigEntryState.LOADED:
            continue
        data = entry.runtime_data
        device = (data.state_coordinator.data or {}).get(device_id)
        if device is None:
            continue
        try:
            schedules = await data.client.get_device_schedules(
                device.environment_id, device_id
            )
            out: list[dict[str, Any]] = []
            for sched in schedules:
                full = await data.client.get_schedule(
                    device.environment_id, device_id, sched.id
                )
                setpoints = [
                    {"day": sp.get("Day"), "hour": sp.get("Hour"), "value": sp.get("Value")}
                    for sp in (full.get("Setpoints") or [])
                ]
                out.append(
                    {
                        "id": sched.id,
                        "name": sched.name,
                        "parameter": sched.parameter,
                        "unit": sched.unit,
                        "active": sched.active,
                        "setpoints": setpoints,
                    }
                )
        except ThemoError as err:
            connection.send_error(msg["id"], "themo_error", str(err))
            return
        connection.send_result(msg["id"], {"device_id": device_id, "schedules": out})
        return
    connection.send_error(msg["id"], "not_found", f"Unknown device_id {device_id}")
