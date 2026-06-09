"""Themo climate platform."""

from __future__ import annotations

from typing import Any

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from homeassistant.exceptions import HomeAssistantError

from . import ThemoConfigEntry
from .api import ThemoDevice, ThemoSchedule
from .const import MODE_MANUAL, MODE_OFF, MODE_SLS, PARAM_MIN_TEMPERATURE
from .coordinator import ThemoScheduleCoordinator, ThemoStateCoordinator
from .entity import ThemoBaseEntity

THEMO_TO_HA = {MODE_OFF: HVACMode.OFF, MODE_MANUAL: HVACMode.HEAT, MODE_SLS: HVACMode.AUTO}
HA_TO_THEMO = {v: k for k, v in THEMO_TO_HA.items()}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ThemoConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data.state_coordinator
    schedule_coordinator = entry.runtime_data.schedule_coordinator
    async_add_entities(
        ThemoClimate(coordinator, device, schedule_coordinator)
        for device in coordinator.data.values()
    )


class ThemoClimate(ThemoBaseEntity, ClimateEntity):
    """A Themo thermostat as a climate entity."""

    _attr_name = None
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_target_temperature_step = 0.5
    _attr_min_temp = 5.0
    _attr_max_temp = 35.0
    _attr_hvac_modes = [HVACMode.OFF, HVACMode.HEAT, HVACMode.AUTO]

    def __init__(
        self,
        coordinator: ThemoStateCoordinator,
        device: ThemoDevice,
        schedule_coordinator: ThemoScheduleCoordinator,
    ) -> None:
        super().__init__(coordinator, device)
        self._attr_unique_id = f"{device.id}_climate"
        self._optimistic_target: float | None = None
        self._optimistic_mode: HVACMode | None = None
        self._schedule_coordinator = schedule_coordinator

    @callback
    def _handle_coordinator_update(self) -> None:
        # Fresh poll arrived: drop optimistic overrides and reconcile.
        self._optimistic_target = None
        self._optimistic_mode = None
        super()._handle_coordinator_update()

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(
            self._schedule_coordinator.async_add_listener(self.async_write_ha_state)
        )

    def _schedules(self) -> list[ThemoSchedule]:
        data = self._schedule_coordinator.data or {}
        return data.get(self._device_id, [])

    @property
    def hvac_mode(self) -> HVACMode:
        if self._optimistic_mode is not None:
            return self._optimistic_mode
        if self.device.state is None:
            return HVACMode.OFF
        return THEMO_TO_HA.get(self.device.state.mode, HVACMode.OFF)

    @property
    def hvac_action(self) -> HVACAction:
        if self.hvac_mode == HVACMode.OFF:
            return HVACAction.OFF
        if self.device.state is None:
            return HVACAction.IDLE
        return HVACAction.HEATING if self.device.state.load_state else HVACAction.IDLE

    @property
    def current_temperature(self) -> float | None:
        if self.device.state is None:
            return None
        # Info is the thermostat's active/displayed temperature, which can differ
        # from the raw room sensor (RT) on combi/floor devices.
        return self.device.state.info

    @property
    def target_temperature(self) -> float | None:
        if self._optimistic_target is not None:
            return self._optimistic_target
        if self.device.state is None:
            return None
        return self.device.state.manual_temperature

    @property
    def supported_features(self) -> ClimateEntityFeature:
        features = (
            ClimateEntityFeature.TURN_ON
            | ClimateEntityFeature.TURN_OFF
            | ClimateEntityFeature.PRESET_MODE
        )
        if self.hvac_mode is HVACMode.HEAT:
            features |= ClimateEntityFeature.TARGET_TEMPERATURE
        return features

    @property
    def preset_modes(self) -> list[str] | None:
        names = [s.name for s in self._schedules() if s.parameter == PARAM_MIN_TEMPERATURE]
        return names or None

    @property
    def preset_mode(self) -> str | None:
        for schedule in self._schedules():
            if schedule.parameter == PARAM_MIN_TEMPERATURE and schedule.active:
                return schedule.name
        return None

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        schedule = next(
            (
                s
                for s in self._schedules()
                if s.parameter == PARAM_MIN_TEMPERATURE and s.name == preset_mode
            ),
            None,
        )
        if schedule is None:
            raise HomeAssistantError(f"Unknown schedule: {preset_mode}")
        await self.coordinator.client.activate_schedule(
            self.device.environment_id, self.device.id, schedule.id, schedule.name
        )
        await self._schedule_coordinator.async_request_refresh()

    async def async_set_temperature(self, **kwargs: Any) -> None:
        temperature = kwargs.get(ATTR_TEMPERATURE)
        if temperature is None:
            return
        await self.coordinator.client.send_command(
            self.device.environment_id, self.device.id, {"CMT": temperature}
        )
        self._optimistic_target = temperature
        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        themo_mode = HA_TO_THEMO.get(hvac_mode)
        if themo_mode is None:
            return
        await self.coordinator.client.send_command(
            self.device.environment_id, self.device.id, {"CMode": themo_mode}
        )
        self._optimistic_mode = hvac_mode
        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()
