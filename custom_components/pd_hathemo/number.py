"""Themo price-limit (number) platform.

The Themo API stores the limit in EUR/MWh; Home Assistant shows it in c/kWh
(1 c/kWh = 10 EUR/MWh). A write is readable back from the API immediately, so the
settings coordinator's data is updated in place after a successful write.
"""

from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import ThemoConfigEntry
from .api import ThemoDevice
from .coordinator import ThemoSettingsCoordinator, ThemoStateCoordinator
from .entity import ThemoBaseEntity

EUR_MWH_PER_CENT_KWH = 10


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ThemoConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data.state_coordinator
    settings_coordinator = entry.runtime_data.settings_coordinator
    async_add_entities(
        ThemoPriceLimitNumber(coordinator, device, settings_coordinator)
        for device in coordinator.data.values()
    )


class ThemoPriceLimitNumber(ThemoBaseEntity, NumberEntity):
    """Electricity price above which Themo's optimization does not heat."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_translation_key = "price_limit"
    _attr_native_unit_of_measurement = "c/kWh"
    _attr_native_min_value = 0
    _attr_native_max_value = 500
    _attr_native_step = 0.1
    _attr_mode = NumberMode.BOX

    def __init__(
        self,
        coordinator: ThemoStateCoordinator,
        device: ThemoDevice,
        settings_coordinator: ThemoSettingsCoordinator,
    ) -> None:
        super().__init__(coordinator, device)
        self._attr_unique_id = f"{device.id}_price_limit"
        self._settings_coordinator = settings_coordinator

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(
            self._settings_coordinator.async_add_listener(self.async_write_ha_state)
        )

    @property
    def available(self) -> bool:
        return super().available and self._device_id in (
            self._settings_coordinator.data or {}
        )

    @property
    def native_value(self) -> float | None:
        limit = (self._settings_coordinator.data or {}).get(self._device_id)
        if limit is None:
            return None
        return round(limit / EUR_MWH_PER_CENT_KWH, 3)

    async def async_set_native_value(self, value: float) -> None:
        limit = round(value * EUR_MWH_PER_CENT_KWH, 3)
        await self.coordinator.client.set_limit_price(
            self.device.environment_id, self.device.id, limit
        )
        self._settings_coordinator.async_set_updated_data(
            {**(self._settings_coordinator.data or {}), self._device_id: limit}
        )
