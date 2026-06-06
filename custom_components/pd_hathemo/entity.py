"""Base entity for Themo devices."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import ThemoDevice
from .const import DOMAIN
from .coordinator import ThemoStateCoordinator


class ThemoBaseEntity(CoordinatorEntity[ThemoStateCoordinator]):
    """Common base wiring device lookup + DeviceInfo."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: ThemoStateCoordinator, device: ThemoDevice) -> None:
        super().__init__(coordinator)
        self._device_id = device.id
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, str(device.id))},
            name=device.name,
            manufacturer="Themo",
            model=device.model,
            sw_version=device.sw_version,
        )

    @property
    def device(self) -> ThemoDevice:
        """The current device snapshot from the coordinator."""
        return self.coordinator.data[self._device_id]

    @property
    def available(self) -> bool:
        return (
            super().available
            and self._device_id in self.coordinator.data
            and self.device.state is not None
        )
