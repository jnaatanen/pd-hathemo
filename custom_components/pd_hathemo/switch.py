"""Themo child-lock (switch) platform.

State.Lock reflects a CLock command after roughly 10 seconds. The switch shows the
commanded value right away and keeps it through at most one poll that still carries
the old value; after that the device-reported state wins.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import ThemoConfigEntry
from .api import ThemoDevice
from .coordinator import ThemoStateCoordinator
from .entity import ThemoBaseEntity

LOCK_OFF = 0
LOCK_ON = 1
LOCK_HARD = 2


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ThemoConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data.state_coordinator
    async_add_entities(
        ThemoChildLockSwitch(coordinator, device)
        for device in coordinator.data.values()
    )


class ThemoChildLockSwitch(ThemoBaseEntity, SwitchEntity):
    """The thermostat's child lock (button lock)."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_translation_key = "child_lock"

    def __init__(
        self, coordinator: ThemoStateCoordinator, device: ThemoDevice
    ) -> None:
        super().__init__(coordinator, device)
        self._attr_unique_id = f"{device.id}_child_lock"
        self._optimistic: bool | None = None
        self._stale_polls = 0

    def _reported(self) -> bool | None:
        state = self.device.state
        if state is None or state.lock is None:
            return None
        return state.lock in (LOCK_ON, LOCK_HARD)

    @callback
    def _handle_coordinator_update(self) -> None:
        if self._optimistic is not None:
            if self._reported() == self._optimistic or self._stale_polls >= 1:
                self._optimistic = None
            else:
                self._stale_polls += 1
        super()._handle_coordinator_update()

    @property
    def is_on(self) -> bool | None:
        if self._optimistic is not None:
            return self._optimistic
        return self._reported()

    async def _set(self, value: int) -> None:
        await self.coordinator.client.send_command(
            self.device.environment_id, self.device.id, {"CLock": value}
        )
        self._optimistic = value != LOCK_OFF
        self._stale_polls = 0
        self.async_write_ha_state()

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._set(LOCK_ON)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._set(LOCK_OFF)
