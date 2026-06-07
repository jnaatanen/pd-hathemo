"""Daily heating-time accumulator for Themo devices.

State.LS is a binary on/off indicator of the heating element. This tracks how many
seconds the element has been on during the current local day, fed one sample per
state poll. Only `day` and `on_seconds` are persisted; timing state is re-seeded after
a restart, so a downtime gap is counted as not-heating.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any


@dataclass
class DailyHeatingTracker:
    """Accumulates heating-on seconds for the current local day."""

    day: date | None = None
    on_seconds: float = 0.0
    last_ts: datetime | None = field(default=None, repr=False)
    last_heating: bool = field(default=False, repr=False)

    def update(self, now: datetime, heating: bool, day: date) -> None:
        """Account the interval since the last sample, then store this sample."""
        if self.day != day:
            self.day = day
            self.on_seconds = 0.0
            self.last_ts = now
            self.last_heating = heating
            return
        if self.last_ts is not None:
            delta = (now - self.last_ts).total_seconds()
            if delta > 0 and self.last_heating:
                self.on_seconds += delta
        self.last_ts = now
        self.last_heating = heating

    def to_storage(self) -> dict[str, Any]:
        """Serialize the persisted fields."""
        return {
            "day": self.day.isoformat() if self.day else None,
            "on_seconds": self.on_seconds,
        }

    @classmethod
    def from_storage(cls, data: dict[str, Any]) -> "DailyHeatingTracker":
        """Restore from persisted fields; timing re-seeds on first update."""
        day_str = data.get("day")
        return cls(
            day=date.fromisoformat(day_str) if day_str else None,
            on_seconds=float(data.get("on_seconds", 0.0)),
        )
