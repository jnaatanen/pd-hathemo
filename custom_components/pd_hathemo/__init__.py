"""The pd_hathemo (Themo) integration."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.httpx_client import get_async_client

from .api import ThemoApiClient, ThemoAuthError, ThemoConnectionError
from .const import PLATFORMS
from .coordinator import ThemoEnergyCoordinator, ThemoStateCoordinator


@dataclass
class ThemoRuntimeData:
    """Objects stored on the config entry at runtime."""

    client: ThemoApiClient
    state_coordinator: ThemoStateCoordinator
    energy_coordinator: ThemoEnergyCoordinator


type ThemoConfigEntry = ConfigEntry[ThemoRuntimeData]


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
    # Non-blocking: an energy import failure must not block setup. Auth is already
    # validated by the state coordinator's first refresh above.
    await energy_coordinator.async_refresh()

    entry.runtime_data = ThemoRuntimeData(
        client=client,
        state_coordinator=state_coordinator,
        energy_coordinator=energy_coordinator,
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ThemoConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
