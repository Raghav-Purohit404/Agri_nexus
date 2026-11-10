"""Persistent PostgreSQL job queue with leases, idempotent enqueue, and retryable workers."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
import inspect
from typing import Any, Awaitable, Callable
from uuid import UUID, uuid4

from sqlalchemy import or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session


def _canonical_hash(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return sha256(payload.encode("utf-8")).hexdigest()


class PostgresJobQueue:
    """Job persistence operations; transaction ownership remains with the caller."""

    def __init__(self, session: Session, model: type[Any] | None = None) -> None:
        if model is None:
            from farm_twin.db.models import AsyncJobORM
            model = AsyncJobORM
        self.session = session
        self.model = model

    def enqueue(
        self, tenant_id: str, kind: str, payload: dict[str, Any], idempotency_key: str,
    ) -> dict[str, Any]:
        if not tenant_id or not kind or not idempotency_key:
            raise ValueError("tenant, job kind, and idempotency key are required")
        digest = _canonical_hash(payload)
        statement = (
            insert(self.model)
            .values(id=uuid4(), tenant_id=tenant_id, kind=kind, payload=payload, status="QUEUED",
                    idempotency_key=idempotency_key, request_hash=digest)
            .on_conflict_do_nothing(index_elements=[self.model.tenant_id, self.model.kind, self.model.idempotency_key])
        )
        inserted = self.session.execute(statement).rowcount
        row = self.session.scalar(
            select(self.model).where(self.model.tenant_id == tenant_id,
                                     self.model.kind == kind,
                                     self.model.idempotency_key == idempotency_key)
        )
        if row is None:
            raise RuntimeError("idempotent job insertion did not return a job")
        if row.request_hash != digest:
            raise ValueError("Idempotency-Key was already used with a different request payload")
        return {"job_id": str(row.id), "status": row.status, "created": bool(inserted)}

    def claim(self, *, limit: int = 1, lease_seconds: int = 300, now: datetime | None = None) -> list[Any]:
        if limit < 1 or lease_seconds < 1:
            raise ValueError("limit and lease duration must be positive")
        instant = now or datetime.now(timezone.utc)
        statement = (
            select(self.model)
            .where(or_(self.model.status == "QUEUED",
                       (self.model.status == "RUNNING") & (self.model.lease_expires_at < instant)))
            .order_by(self.model.created_at, self.model.id)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        rows = list(self.session.scalars(statement))
        for row in rows:
            row.status = "RUNNING"
            row.started_at = instant
            row.lease_expires_at = instant + timedelta(seconds=lease_seconds)
            row.attempts += 1
        self.session.flush()
        return rows

    def complete(self, job_id: UUID, result: dict[str, Any], now: datetime | None = None) -> None:
        row = self.session.get(self.model, job_id)
        if row is None or row.status != "RUNNING":
            raise ValueError("only a claimed job can be completed")
        row.status = "SUCCEEDED"
        row.result = result
        row.error = None
        row.finished_at = now or datetime.now(timezone.utc)
        row.lease_expires_at = None
        self.session.flush()

    def fail(self, job_id: UUID, error: dict[str, Any], *, max_attempts: int = 5,
             retry_delay_seconds: int = 30, now: datetime | None = None) -> None:
        instant = now or datetime.now(timezone.utc)
        row = self.session.get(self.model, job_id)
        if row is None or row.status != "RUNNING":
            raise ValueError("only a claimed job can fail")
        row.error = error
        row.lease_expires_at = None
        if row.attempts >= max_attempts:
            row.status = "FAILED"
            row.finished_at = instant
        else:
            row.status = "QUEUED"
            row.created_at = instant + timedelta(seconds=retry_delay_seconds * min(32, 2 ** (row.attempts - 1)))
        self.session.flush()


JobHandler = Callable[[dict[str, Any]], dict[str, Any] | Awaitable[dict[str, Any]]]


async def run_worker(
    session_factory: Callable[[], Session],
    handlers: dict[str, JobHandler],
    stop: asyncio.Event,
    *,
    poll_seconds: float = 1.0,
    lease_seconds: int = 300,
    max_attempts: int = 5,
) -> None:
    """Run one worker process. Handlers must be idempotent because leases provide at-least-once delivery."""
    if poll_seconds <= 0:
        raise ValueError("poll interval must be positive")
    while not stop.is_set():
        with session_factory() as session, session.begin():
            rows = PostgresJobQueue(session).claim(limit=1, lease_seconds=lease_seconds)
            claimed = [(row.id, row.kind, dict(row.payload), row.attempts) for row in rows]
        if not claimed:
            try:
                await asyncio.wait_for(stop.wait(), timeout=poll_seconds)
            except TimeoutError:
                pass
            continue
        job_id, kind, payload, attempts = claimed[0]
        handler = handlers.get(kind)
        try:
            if handler is None:
                raise LookupError(f"no worker handler registered for {kind!r}")
            if inspect.iscoroutinefunction(handler):
                result = await handler(payload)
            else:
                result = await asyncio.to_thread(handler, payload)
                if asyncio.isawaitable(result):
                    result = await result
            if not isinstance(result, dict):
                raise TypeError("job handler must return a JSON object")
            with session_factory() as session, session.begin():
                PostgresJobQueue(session).complete(job_id, result)
        except Exception as exc:
            with session_factory() as session, session.begin():
                PostgresJobQueue(session).fail(
                    job_id, {"type": type(exc).__name__, "message": str(exc)}, max_attempts=max_attempts,
                )
