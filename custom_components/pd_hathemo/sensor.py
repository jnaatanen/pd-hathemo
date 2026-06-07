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
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from . import ThemoConfigEntry
from .api import DeviceState, ThemoDevice
from .const import SECONDS_PER_DAY
from .coordinator import ThemoStateCoordinator
from .entity import ThemoBaseEntity
from .heating import DailyHeatingTracker


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
    trackers = entry.runtime_data.heating_trackers
    entities: list[SensorEntity] = []
    for device in coordinator.data.values():
        entities.extend(build_sensors(coordinator, device))
        entities.append(ThemoHeatingTodayRunningSensor(coordinator, device, trackers))
        entities.append(ThemoHeatingTodayCumulativeSensor(coordinator, device, trackers))
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


class ThemoHeatingTodayRunningSensor(ThemoBaseEntity, SensorEntity):
    """Share of the elapsed day so far that the heating element has been on."""

    _attr_translation_key = "heating_today_running"
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self,
        coordinator: ThemoStateCoordinator,
        device: ThemoDevice,
        trackers: dict[int, DailyHeatingTracker],
    ) -> None:
        super().__init__(coordinator, device)
        self._trackers = trackers
        self._attr_unique_id = f"{device.id}_heating_today_running"

    @property
    def available(self) -> bool:
        # Value comes from accumulated time, not the live state, so stay available
        # through transient polls that return no state.
        return (
            self.coordinator.last_update_success
            and self._device_id in self.coordinator.data
        )

    @property
    def native_value(self) -> float | None:
        tracker = self._trackers.get(self._device_id)
        if tracker is None:
            return None
        elapsed = (dt_util.now() - dt_util.start_of_local_day()).total_seconds()
        if elapsed <= 0:
            return None
        return round(tracker.on_seconds / elapsed * 100, 1)


class ThemoHeatingTodayCumulativeSensor(ThemoBaseEntity, SensorEntity):
    """Share of the full 24 h day so far that the heating element has been on."""

    _attr_translation_key = "heating_today_total"
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self,
        coordinator: ThemoStateCoordinator,
        device: ThemoDevice,
        trackers: dict[int, DailyHeatingTracker],
    ) -> None:
        super().__init__(coordinator, device)
        self._trackers = trackers
        self._attr_unique_id = f"{device.id}_heating_today_total"

    @property
    def available(self) -> bool:
        # Value comes from accumulated time, not the live state, so stay available
        # through transient polls that return no state.
        return (
            self.coordinator.last_update_success
            and self._device_id in self.coordinator.data
        )

    @property
    def native_value(self) -> float | None:
        tracker = self._trackers.get(self._device_id)
        if tracker is None:
            return None
        return round(tracker.on_seconds / SECONDS_PER_DAY * 100, 1)
