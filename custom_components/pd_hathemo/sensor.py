"""Themo sensor platform."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

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
from .api import DeviceState, ThemoDevice, ThemoSchedule
from .const import PARAM_MIN_TEMPERATURE, SECONDS_PER_DAY
from .coordinator import ThemoScheduleCoordinator, ThemoStateCoordinator
from .entity import ThemoBaseEntity
from .heating import DailyHeatingTracker
from .schedule import next_change, setpoint_at, upcoming_changes

SCHEDULE_UPCOMING_HOURS = 48


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
    schedules = entry.runtime_data.schedule_coordinator
    entities: list[SensorEntity] = []
    for device in coordinator.data.values():
        entities.extend(build_sensors(coordinator, device))
        entities.append(ThemoHeatingTodayRunningSensor(coordinator, device, trackers))
        entities.append(ThemoHeatingTodayCumulativeSensor(coordinator, device, trackers))
        entities.append(ThemoScheduleTemperatureSensor(coordinator, device, schedules))
        entities.append(ThemoScheduleNextChangeSensor(coordinator, device, schedules))
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


class _ThemoScheduleSensor(ThemoBaseEntity, SensorEntity):
    """Base for sensors derived from the active MinTemperature schedule.

    Schedule hours are wall-clock hours, read here in Home Assistant's time zone.
    """

    def __init__(
        self,
        coordinator: ThemoStateCoordinator,
        device: ThemoDevice,
        schedule_coordinator: ThemoScheduleCoordinator,
    ) -> None:
        super().__init__(coordinator, device)
        self._schedule_coordinator = schedule_coordinator

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(
            self._schedule_coordinator.async_add_listener(self.async_write_ha_state)
        )

    def _active_schedule(self) -> ThemoSchedule | None:
        data = self._schedule_coordinator.data or {}
        for schedule in data.get(self._device_id, []):
            if (
                schedule.active
                and schedule.parameter == PARAM_MIN_TEMPERATURE
                and schedule.setpoints
            ):
                return schedule
        return None


class ThemoScheduleTemperatureSensor(_ThemoScheduleSensor):
    """The active schedule's setpoint for the current hour."""

    _attr_translation_key = "schedule_temperature"
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_state_class = SensorStateClass.MEASUREMENT
    _unrecorded_attributes = frozenset({"upcoming"})

    def __init__(
        self,
        coordinator: ThemoStateCoordinator,
        device: ThemoDevice,
        schedule_coordinator: ThemoScheduleCoordinator,
    ) -> None:
        super().__init__(coordinator, device, schedule_coordinator)
        self._attr_unique_id = f"{device.id}_schedule_temperature"

    @property
    def native_value(self) -> float | None:
        schedule = self._active_schedule()
        if schedule is None:
            return None
        return setpoint_at(schedule.setpoints, dt_util.now())

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        schedule = self._active_schedule()
        if schedule is None:
            return {}
        changes = upcoming_changes(
            schedule.setpoints, dt_util.now(), SCHEDULE_UPCOMING_HOURS
        )
        return {
            "schedule": schedule.name,
            "upcoming": [
                {"start": start.isoformat(), "temperature": value}
                for start, value in changes
            ],
        }


class ThemoScheduleNextChangeSensor(_ThemoScheduleSensor):
    """When the active schedule's setpoint changes next."""

    _attr_translation_key = "schedule_next_change"
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(
        self,
        coordinator: ThemoStateCoordinator,
        device: ThemoDevice,
        schedule_coordinator: ThemoScheduleCoordinator,
    ) -> None:
        super().__init__(coordinator, device, schedule_coordinator)
        self._attr_unique_id = f"{device.id}_schedule_next_change"

    def _next(self) -> tuple[datetime, float] | None:
        schedule = self._active_schedule()
        if schedule is None:
            return None
        return next_change(schedule.setpoints, dt_util.now())

    @property
    def native_value(self) -> datetime | None:
        change = self._next()
        return None if change is None else change[0]

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        change = self._next()
        return {} if change is None else {"temperature": change[1]}
