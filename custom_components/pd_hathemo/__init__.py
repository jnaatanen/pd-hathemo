"""The pd_hathemo (Themo) integration."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.httpx_client import get_async_client
from homeassistant.helpers.storage import Store
from homeassistant.helpers.typing import ConfigType
from homeassistant.util import dt as dt_util

from .api import ThemoApiClient, ThemoAuthError, ThemoConnectionError
from .const import PLATFORMS, STORAGE_KEY, STORAGE_VERSION
from .coordinator import (
    ThemoEnergyCoordinator,
    ThemoScheduleCoordinator,
    ThemoStateCoordinator,
)
from .heating import DailyHeatingTracker
from .websocket import async_register_websocket_commands


@dataclass
class ThemoRuntimeData:
    """Objects stored on the config entry at runtime."""

    client: ThemoApiClient
    state_coordinator: ThemoStateCoordinator
    energy_coordinator: ThemoEnergyCoordinator
    heating_trackers: dict[int, DailyHeatingTracker]
    schedule_coordinator: ThemoScheduleCoordinator


type ThemoConfigEntry = ConfigEntry[ThemoRuntimeData]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register integration-wide websocket commands."""
    async_register_websocket_commands(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ThemoConfigEntry) -> bool:
    """Set up Themo from a config entry."""
    client = ThemoApiClient(
        entry.data[CONF_USERNAME],
        entry.data[CONF_PASSWORD],
        get_async_client(hass),
    )
    try:
        await client.authenticate()
        environments = await client.get_environments()
    except ThemoAuthError as err:
        raise ConfigEntryAuthFailed(str(err)) from err
    except ThemoConnectionError as err:
        raise ConfigEntryNotReady(str(err)) from err

    env_ids = [int(env["Id"]) for env in environments]

    state_coordinator = ThemoStateCoordinator(hass, client, env_ids)
    await state_coordinator.async_config_entry_first_refresh()

    energy_coordinator = ThemoEnergyCoordinator(hass, client, state_coordinator)
    # This coordinator has no entities. A DataUpdateCoordinator only schedules its
    # periodic refresh while it has at least one listener, so register a permanent
    # no-op listener to keep the ENERGY_SCAN_INTERVAL polling alive. Without it the
    # energy import would only run at setup/reload.
    entry.async_on_unload(energy_coordinator.async_add_listener(lambda: None))
    # Non-blocking: an energy import failure must not block setup. Auth is already
    # validated by the state coordinator's first refresh above.
    await energy_coordinator.async_refresh()

    # Daily heating-time trackers (one per device), persisted across restarts.
    store: Store = Store(hass, STORAGE_VERSION, STORAGE_KEY)
    stored = await store.async_load() or {}
    trackers: dict[int, DailyHeatingTracker] = {}
    for device in state_coordinator.data.values():
        saved = stored.get(str(device.id))
        trackers[device.id] = (
            DailyHeatingTracker.from_storage(saved) if saved else DailyHeatingTracker()
        )

    @callback
    def _update_trackers() -> None:
        now = dt_util.utcnow()
        today = dt_util.now().date()
        for dev in state_coordinator.data.values():
            if dev.state is None:
                continue
            tracker = trackers.get(dev.id)
            if tracker is None:
                tracker = trackers[dev.id] = DailyHeatingTracker()
            tracker.update(now, dev.state.load_state == 1, today)
        store.async_delay_save(
            lambda: {str(k): t.to_storage() for k, t in trackers.items()}, 30
        )

    entry.async_on_unload(state_coordinator.async_add_listener(_update_trackers))
    _update_trackers()  # seed an initial sample so values start moving

    async def _flush_trackers() -> None:
        await store.async_save({str(k): t.to_storage() for k, t in trackers.items()})

    entry.async_on_unload(_flush_trackers)

    schedule_coordinator = ThemoScheduleCoordinator(hass, client, state_coordinator)
    # Schedules are non-critical; a failure must not block setup.
    await schedule_coordinator.async_refresh()

    entry.runtime_data = ThemoRuntimeData(
        client=client,
        state_coordinator=state_coordinator,
        energy_coordinator=energy_coordinator,
        heating_trackers=trackers,
        schedule_coordinator=schedule_coordinator,
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ThemoConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
