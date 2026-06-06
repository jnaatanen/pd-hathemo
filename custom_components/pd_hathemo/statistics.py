"""Transform Themo hourly data into Home Assistant long-term statistics."""

from __future__ import annotations

from datetime import datetime, timezone
import logging
from typing import Any

from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.models import StatisticData, StatisticMetaData
from homeassistant.components.recorder.statistics import (
    async_add_external_statistics,
    get_last_statistics,
)
from homeassistant.const import UnitOfEnergy
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .api import ThemoDevice
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

ENERGY_SERIES_NAME = "Price data"
ENERGY_COLUMN_NAME = "Consumption"
MWH_TO_KWH = 1000.0


def statistic_id_for(device: ThemoDevice) -> str:
    """External statistic id for a device's energy (must contain a colon)."""
    return f"{DOMAIN}:energy_{device.id}"


def extract_hourly_kwh(series_list: list[dict[str, Any]]) -> list[tuple[datetime, float]]:
    """Return [(utc_hour, kWh)] from the 'Price data'/'Consumption' column.

    Skips datapoints with a missing/None consumption value (e.g. the current
    incomplete hour). Timestamps are epoch milliseconds.
    """
    for series in series_list:
        if series.get("Name") != ENERGY_SERIES_NAME:
            continue
        definitions = series.get("TimeSeriesDefinitions") or []
        idx = next(
            (i for i, d in enumerate(definitions) if d.get("Name") == ENERGY_COLUMN_NAME),
            None,
        )
        if idx is None:
            return []
        points: list[tuple[datetime, float]] = []
        for point in series.get("TimeSeries") or []:
            values = point.get("Values") or []
            if idx >= len(values):
                continue
            value = values[idx]
            if value is None:
                continue
            ts = datetime.fromtimestamp(point["Time"] / 1000, tz=timezone.utc)
            points.append((ts, value * MWH_TO_KWH))
        points.sort(key=lambda item: item[0])
        return points
    return []


def build_statistics(
    points: list[tuple[datetime, float]],
    last_sum: float,
    last_start: datetime | None,
) -> list[StatisticData]:
    """Build cumulative-sum statistics, skipping already-imported hours."""
    result: list[StatisticData] = []
    running = last_sum
    for ts, kwh in points:
        if last_start is not None and ts <= last_start:
            continue
        running += kwh
        result.append(StatisticData(start=ts, state=running, sum=running))
    return result


async def async_import_device_energy(
    hass: HomeAssistant, device: ThemoDevice, series_list: list[dict[str, Any]]
) -> None:
    """Import a device's hourly consumption as external long-term statistics."""
    points = extract_hourly_kwh(series_list)
    if not points:
        return

    statistic_id = statistic_id_for(device)
    last_stat = await get_instance(hass).async_add_executor_job(
        get_last_statistics, hass, 1, statistic_id, True, {"sum"}
    )
    if last_stat.get(statistic_id):
        row = last_stat[statistic_id][0]
        last_sum = float(row["sum"] or 0.0)
        last_start = dt_util.utc_from_timestamp(row["start"])
    else:
        last_sum = 0.0
        last_start = None

    stats = build_statistics(points, last_sum, last_start)
    if not stats:
        return

    metadata = StatisticMetaData(
        has_mean=False,
        has_sum=True,
        name=f"{device.name} energy",
        source=DOMAIN,
        statistic_id=statistic_id,
        unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
    )
    async_add_external_statistics(hass, metadata, stats)
