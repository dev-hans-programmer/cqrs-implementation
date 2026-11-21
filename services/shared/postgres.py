from __future__ import annotations

import json
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any, TypeAlias

import asyncpg

from .events import EventEnvelope

if TYPE_CHECKING:
    DbConnection: TypeAlias = (
        asyncpg.Connection[asyncpg.Record] | asyncpg.pool.PoolConnectionProxy[asyncpg.Record]
    )
else:
    DbConnection = Any

COMMON_SCHEMA = """
CREATE TABLE IF NOT EXISTS outbox_events (
    id TEXT PRIMARY KEY,
    event_name TEXT NOT NULL,
    aggregate_id TEXT NOT NULL,
    payload JSONB NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL,
    published_at TIMESTAMPTZ,
    attempts INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_outbox_unpublished
    ON outbox_events (occurred_at) WHERE published_at IS NULL;

CREATE TABLE IF NOT EXISTS inbox_events (
    event_id TEXT PRIMARY KEY,
    event_name TEXT NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""


class PostgresRuntime:
    """Owns a service-local asyncpg pool and common delivery tables."""

    def __init__(self, dsn: str) -> None:
        self._dsn = dsn
        self.pool: asyncpg.Pool | None = None

    async def connect(self, service_schema: str) -> None:
        self.pool = await asyncpg.create_pool(self._dsn, min_size=2, max_size=10)
        async with self.require_pool().acquire() as connection:
            await connection.execute(COMMON_SCHEMA)
            await connection.execute(service_schema)

    async def close(self) -> None:
        if self.pool is not None:
            await self.pool.close()
            self.pool = None

    def require_pool(self) -> asyncpg.Pool:
        if self.pool is None:
            raise RuntimeError("PostgreSQL runtime has not been started")
        return self.pool


async def append_outbox(connection: DbConnection, event: EventEnvelope) -> None:
    await connection.execute(
        """
        INSERT INTO outbox_events(id, event_name, aggregate_id, payload, occurred_at)
        VALUES($1, $2, $3, $4::jsonb, $5)
        ON CONFLICT (id) DO NOTHING
        """,
        event.id,
        event.name,
        event.aggregate_id,
        json.dumps(event.payload),
        event.occurred_at,
    )


def json_value(value: Any) -> Any:
    """asyncpg returns JSON as text unless a custom codec was registered."""

    return json.loads(value) if isinstance(value, str) else value


def rows_to_dicts(rows: Sequence[asyncpg.Record]) -> list[dict[str, Any]]:
    return [dict(row) for row in rows]
