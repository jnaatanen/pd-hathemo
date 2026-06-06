"""Data update coordinators for the Themo integration."""

from __future__ import annotations

from datetime import timedelta
import logging

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import ThemoApiClient, ThemoAuthError, ThemoConnectionError, ThemoDevice
from .const import (
    DOMAIN,
    ENERGY_BACKFILL_DAYS,
    ENERGY_INCREMENTAL_DAYS,
    ENERGY_SCAN_INTERVAL,
    STATE_SCAN_INTERVAL,
)
from .statistics import async_import_device_energy

_LOGGER = logging.getLogger(__name__)


class ThemoStateCoordinator(DataUpdateCoordinator[dict[int, ThemoDevice]]):
    """Polls device state for all environments every STATE_SCAN_INTERVAL."""

    def __init__(
        self, hass: HomeAssistant, client: ThemoApiClient, environment_ids: list[int]
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN} state",
            update_interval=STATE_SCAN_INTERVAL,
        )
        self.client = client
        self._environment_ids = environment_ids

    async def _async_update_data(self) -> dict[int, ThemoDevice]:
        devices: dict[int, ThemoDevice] = {}
        try:
            for env_id in self._environment_ids:
                for device in await self.client.get_devices(env_id):
                    devices[device.id] = device
        except ThemoAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except ThemoConnectionError as err:
            raise UpdateFailed(str(err)) from err
        return devices


class ThemoEnergyCoordinator(DataUpdateCoordinator[None]):
    """Imports hourly energy consumption as statistics every ENERGY_SCAN_INTERVAL."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: ThemoApiClient,
        state_coordinator: ThemoStateCoordinator,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN} energy",
            update_interval=ENERGY_SCAN_INTERVAL,
        )
        self.client = client
        self._state_coordinator = state_coordinator
        self._backfilled: set[int] = set()

    async def _async_update_data(self) -> None:
        devices = self._state_coordinator.data or {}
        now = dt_util.utcnow()
        for device in devices.values():
            days = (
                ENERGY_BACKFILL_DAYS
                if device.id not in self._backfilled
                else ENERGY_INCREMENTAL_DAYS
            )
            dt_from = now - timedelta(days=days)
            try:
                series = await self.client.get_device_data(
                    device.environment_id, device.id, dt_from, now
                )
                await async_import_device_energy(self.hass, device, series)
                self._backfilled.add(device.id)
            except ThemoAuthError as err:
                raise ConfigEntryAuthFailed(str(err)) from err
            except ThemoConnectionError as err:
                _LOGGER.warning(
                    "Energy update failed for %s: %s", device.name, err
                )
        return None
