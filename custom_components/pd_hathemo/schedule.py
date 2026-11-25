"""Pure helpers for Themo weekly schedules.

A schedule is a grid of hourly setpoints keyed by (day, hour), where day follows the
Themo API: 0 = Sunday .. 6 = Saturday. Hours are wall-clock hours at the thermostat.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

Grid = dict[tuple[int, int], float]

HOURS_PER_WEEK = 168


def grid_from_setpoints(setpoints: list[dict[str, Any]] | None) -> Grid:
    """Build a grid from the API's Setpoints list, skipping incomplete points."""
    grid: Grid = {}
    for point in setpoints or []:
        day, hour, value = point.get("Day"), point.get("Hour"), point.get("Value")
        if day is None or hour is None or value is None:
            continue
        grid[(int(day), int(hour))] = value
    return grid


def _key(when: datetime) -> tuple[int, int]:
    # Python: Monday = 0 .. Sunday = 6; Themo: Sunday = 0 .. Saturday = 6.
    return ((when.weekday() + 1) % 7, when.hour)


def setpoint_at(grid: Grid, when: datetime) -> float | None:
    """Setpoint for the wall-clock hour of `when` (an aware local datetime)."""
    return grid.get(_key(when))


def upcoming_changes(
    grid: Grid, when: datetime, hours: int
) -> list[tuple[datetime, float]]:
    """Setpoint changes within the next `hours` hours, as (start, new value)."""
    changes: list[tuple[datetime, float]] = []
    hour_start = when.replace(minute=0, second=0, microsecond=0)
    current = setpoint_at(grid, hour_start)
    for offset in range(1, hours + 1):
        start = hour_start + timedelta(hours=offset)
        value = setpoint_at(grid, start)
        if value is None or value == current:
            continue
        changes.append((start, value))
        current = value
    return changes


def next_change(grid: Grid, when: datetime) -> tuple[datetime, float] | None:
    """The next setpoint change within a week, or None if the grid is constant."""
    hour_start = when.replace(minute=0, second=0, microsecond=0)
    current = setpoint_at(grid, hour_start)
    for offset in range(1, HOURS_PER_WEEK + 1):
        start = hour_start + timedelta(hours=offset)
        value = setpoint_at(grid, start)
        if value is not None and value != current:
            return start, value
    return None
