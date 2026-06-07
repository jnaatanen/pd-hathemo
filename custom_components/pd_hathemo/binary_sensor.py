"""Themo heating-activity binary sensor."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
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
        ThemoHeatingBinarySensor(coordinator, device)
        for device in coordinator.data.values()
    )


class ThemoHeatingBinarySensor(ThemoBaseEntity, BinarySensorEntity):
    """Whether the thermostat's heating element is currently on."""

    _attr_device_class = BinarySensorDeviceClass.RUNNING
    _attr_translation_key = "heating"

    def __init__(
        self, coordinator: ThemoStateCoordinator, device: ThemoDevice
    ) -> None:
        super().__init__(coordinator, device)
        self._attr_unique_id = f"{device.id}_heating"

    @property
    def is_on(self) -> bool | None:
        state = self.device.state
        return None if state is None else state.load_state == 1
