"""Themo sensor platform."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import EntityCategory, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import ThemoConfigEntry
from .api import DeviceState, ThemoDevice
from .coordinator import ThemoStateCoordinator
from .entity import ThemoBaseEntity


@dataclass(frozen=True, kw_only=True)
class ThemoSensorDescription(SensorEntityDescription):
    """Describes a Themo sensor."""

    value_fn: Callable[[DeviceState], float | None]
    exists_fn: Callable[[DeviceState], bool] = lambda _state: True


SENSORS: tuple[ThemoSensorDescription, ...] = (
    ThemoSensorDescription(
        key="room_temperature",
        translation_key="room_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda state: state.room_temperature,
    ),
    ThemoSensorDescription(
        key="floor_temperature",
        translation_key="floor_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda state: state.floor_temperature,
        exists_fn=lambda state: state.is_floor,
    ),
    ThemoSensorDescription(
        key="outside_temperature",
        translation_key="outside_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda state: state.outside_temperature,
    ),
)


def build_sensors(
    coordinator: ThemoStateCoordinator, device: ThemoDevice
) -> list["ThemoSensor"]:
    """Create the sensor entities a device supports."""
    return [
        ThemoSensor(coordinator, device, description)
        for description in SENSORS
        if device.state is not None and description.exists_fn(device.state)
    ]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ThemoConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data.state_coordinator
    entities: list[ThemoSensor] = []
    for device in coordinator.data.values():
        entities.extend(build_sensors(coordinator, device))
    async_add_entities(entities)


class ThemoSensor(ThemoBaseEntity, SensorEntity):
    """A Themo measurement sensor."""

    entity_description: ThemoSensorDescription

    def __init__(
        self,
        coordinator: ThemoStateCoordinator,
        device: ThemoDevice,
        description: ThemoSensorDescription,
    ) -> None:
        super().__init__(coordinator, device)
        self.entity_description = description
        self._attr_unique_id = f"{device.id}_{description.key}"

    @property
    def native_value(self) -> float | None:
        if self.device.state is None:
            return None
        return self.entity_description.value_fn(self.device.state)
