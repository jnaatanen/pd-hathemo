"""Themo backlight (light) platform.

State.Lights does not reliably reflect the live on/off value, so this entity is
optimistic (assumed_state): is_on tracks the last commanded value.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.light import ColorMode, LightEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import ThemoConfigEntry
from .api import ThemoDevice
from .coordinator import ThemoStateCoordinator
from .entity import ThemoBaseEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ThemoConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data.state_coordinator
    async_add_entities(
        ThemoLight(coordinator, device) for device in coordinator.data.values()
    )


class ThemoLight(ThemoBaseEntity, LightEntity):
    """The thermostat backlight."""

    _attr_assumed_state = True
    _attr_translation_key = "backlight"
    _attr_color_mode = ColorMode.ONOFF
    _attr_supported_color_modes = {ColorMode.ONOFF}

    def __init__(
        self, coordinator: ThemoStateCoordinator, device: ThemoDevice
    ) -> None:
        super().__init__(coordinator, device)
        self._attr_unique_id = f"{device.id}_backlight"
        self._attr_is_on = bool(device.state.lights) if device.state else False

    async def _set(self, value: int) -> None:
        await self.coordinator.client.send_command(
            self.device.environment_id, self.device.id, {"CLights": value}
        )
        self._attr_is_on = bool(value)
        self.async_write_ha_state()

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._set(1)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._set(0)
