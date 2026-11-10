"""
FILE: farm_twin/state/events.py
PURPOSE: Event bus + scheduler for the real-time (non-simulation) side: new observation arrives -> state update -> re-forecast -> maybe notify agents.

IMPLEMENT: Event types: ObservationAdded, WeatherForecastUpdated, SatelliteSceneIngested, InterventionExecuted, PriceUpdated, CalibrationPromoted, AnomalyDetected. In-process pub/sub (asyncio) with a durable outbox table (outbox in Postgres) for at-least-once delivery; handlers idempotent.
 Handlers: on ObservationAdded(soil) -> mark plot soil state stale-or-refreshed, trigger `hindcast_and_score`; on WeatherForecastUpdated -> recompute 14-day irrigation advice per cropped plot; on SatelliteScene -> compare model CC vs satellite fcover, create AnomalyDetected if |diff|>0.2 for two scenes; on InterventionExecuted -> update state, create Outcome tracking stub; on PriceUpdated -> invalidate cached financial results.
 Scheduler (APScheduler): daily 05:30 IST weather+forecast pull; weekly satellite pull; nightly calibration check; monthly full re-optimisation proposal (never auto-applied).
TESTS: at-least-once with idempotent handler; ordering within a plot preserved.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable


@dataclass(frozen=True)
class FarmEvent:
    id: str
    kind: str
    payload: dict[str, Any]
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    plot_id: str | None = None


class EventBus:
    """In-process at-least-once dispatcher; durable outbox adapter remains deployment-specific."""

    def __init__(self) -> None:
        self._handlers: dict[str, list[Callable[[FarmEvent], Any]]] = {}
        self._seen: set[tuple[str, str]] = set()
        self._plot_locks: dict[str, asyncio.Lock] = {}

    def subscribe(self, kind: str, handler: Callable[[FarmEvent], Any]) -> None:
        self._handlers.setdefault(kind, []).append(handler)

    async def publish(self, event: FarmEvent) -> None:
        lock = self._plot_locks.setdefault(event.plot_id or "__property__", asyncio.Lock())
        async with lock:
            for i, handler in enumerate(self._handlers.get(event.kind, ())):
                key = (event.id, str(i))
                if key in self._seen:
                    continue
                result = handler(event)
                if asyncio.iscoroutine(result):
                    await result
                self._seen.add(key)


class EventScheduler:
    def __init__(self, bus: EventBus) -> None:
        self.bus = bus

    async def dispatch(self, events: list[FarmEvent]) -> None:
        for event in sorted(events, key=lambda e: (e.plot_id or "", e.created_at, e.id)):
            await self.bus.publish(event)


class DurableOutbox:
    """SQLAlchemy outbox adapter; caller owns transaction boundaries and retries."""

    def __init__(self, session, model=None):
        if model is None:
            from farm_twin.db.models import OutboxORM

            model = OutboxORM
        self.session = session
        self.model = model

    def enqueue(self, event: FarmEvent) -> bool:
        from uuid import uuid4
        from sqlalchemy.dialects.postgresql import insert

        statement = (
            insert(self.model)
            .values(
                id=uuid4(),
                event_id=event.id,
                event_type=event.kind,
                plot_id=event.plot_id,
                payload=event.payload,
                created_at=event.created_at,
            )
            .on_conflict_do_nothing(index_elements=[self.model.event_id])
        )
        return bool(self.session.execute(statement).rowcount)

    def claim(self, limit: int = 100) -> list[object]:
        from sqlalchemy import select

        if limit < 1:
            raise ValueError("claim limit must be positive")
        statement = (
            select(self.model)
            .where(self.model.delivered_at.is_(None))
            .order_by(self.model.created_at, self.model.event_id)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        rows = list(self.session.scalars(statement))
        for row in rows:
            row.attempts += 1
        return rows

    def mark_delivered(self, event_id: str, delivered_at: datetime | None = None) -> bool:
        from sqlalchemy import select

        row = self.session.scalar(
            select(self.model).where(self.model.event_id == event_id).with_for_update()
        )
        if row is None or row.delivered_at is not None:
            return False
        row.delivered_at = delivered_at or datetime.now(timezone.utc)
        return True

    async def deliver_claimed(self, handler: Callable[[FarmEvent], Any], limit: int = 100) -> int:
        """Dispatch after caller claims rows; failed handlers remain pending for at-least-once retry."""
        rows = self.claim(limit)
        delivered = 0
        for row in rows:
            event = FarmEvent(row.event_id, row.event_type, dict(row.payload), row.created_at, str(row.plot_id) if row.plot_id else None)
            result = handler(event)
            if asyncio.iscoroutine(result):
                await result
            self.mark_delivered(row.event_id)
            delivered += 1
        return delivered


async def run_periodic_scheduler(callbacks: dict[str, Callable[[], Any]], stop: asyncio.Event) -> None:
    """UTC-independent scheduler for documented IST jobs; callbacks perform actual work."""
    from datetime import datetime, time as day_time, timedelta
    from zoneinfo import ZoneInfo

    jobs = {
        "weather_forecast": ("daily", day_time(5, 30)),
        "satellite_refresh": ("weekly", day_time(6, 0)),
        "calibration_check": ("daily", day_time(23, 0)),
        "monthly_optimization": ("monthly", day_time(2, 0)),
    }
    zone = ZoneInfo("Asia/Kolkata")

    def next_run(now: datetime, cadence: str, target_time):
        candidate = now.replace(hour=target_time.hour, minute=target_time.minute, second=0, microsecond=0)
        if cadence == "daily":
            return candidate if candidate > now else candidate + timedelta(days=1)
        if cadence == "weekly":
            days = (0 - candidate.weekday()) % 7
            candidate += timedelta(days=days)
            return candidate if candidate > now else candidate + timedelta(days=7)
        candidate = candidate.replace(day=1)
        if candidate > now:
            return candidate
        month = 1 if candidate.month == 12 else candidate.month + 1
        year = candidate.year + int(candidate.month == 12)
        return candidate.replace(year=year, month=month, day=1)

    async def loop(name: str, cadence: str, target_time) -> None:
        callback = callbacks.get(name)
        if callback is None:
            return
        while not stop.is_set():
            now = datetime.now(zone)
            delay = max(0.0, (next_run(now, cadence, target_time) - now).total_seconds())
            try:
                await asyncio.wait_for(stop.wait(), timeout=delay)
                return
            except TimeoutError:
                result = callback()
                if asyncio.iscoroutine(result):
                    await result

    await asyncio.gather(*(loop(name, *schedule) for name, schedule in jobs.items()))
