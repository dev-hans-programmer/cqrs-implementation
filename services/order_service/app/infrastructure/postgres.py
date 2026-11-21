from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal
from typing import Any

import asyncpg

from services.shared.events import EventEnvelope
from services.shared.postgres import DbConnection, PostgresRuntime, append_outbox, json_value

from ..application.ports import OrderView
from ..domain.events import OrderChanged
from ..domain.models import Order, OrderItem, OrderStatus

ORDER_SCHEMA = """
CREATE TABLE IF NOT EXISTS orders (
    id TEXT PRIMARY KEY,
    customer_id TEXT NOT NULL,
    items JSONB NOT NULL,
    total NUMERIC(12, 2) NOT NULL,
    status TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    version INTEGER NOT NULL,
    idempotency_key TEXT UNIQUE
);

CREATE TABLE IF NOT EXISTS order_views (
    id TEXT PRIMARY KEY,
    data JSONB NOT NULL,
    projected_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""


def order_payload(order: Order) -> dict[str, Any]:
    return {
        "id": order.id,
        "customer_id": order.customer_id,
        "items": [{"sku": item.sku, "quantity": item.quantity} for item in order.items],
        "total": str(order.total),
        "status": order.status.value,
        "created_at": order.created_at.isoformat(),
        "version": order.version,
    }


def order_from_payload(data: dict[str, Any]) -> Order:
    return Order(
        id=data["id"],
        customer_id=data["customer_id"],
        items=tuple(OrderItem(item["sku"], item["quantity"]) for item in data["items"]),
        total=Decimal(data["total"]),
        status=OrderStatus(data["status"]),
        created_at=datetime.fromisoformat(data["created_at"]),
        version=data["version"],
    )


class PostgresOrderWriteRepository:
    def __init__(self, runtime: PostgresRuntime) -> None:
        self._runtime = runtime

    async def get(self, order_id: str) -> Order | None:
        async with self._runtime.require_pool().acquire() as connection:
            row = await connection.fetchrow("SELECT * FROM orders WHERE id = $1", order_id)
        return self._from_row(row) if row else None

    async def get_by_idempotency_key(self, key: str) -> Order | None:
        async with self._runtime.require_pool().acquire() as connection:
            row = await connection.fetchrow("SELECT * FROM orders WHERE idempotency_key = $1", key)
        return self._from_row(row) if row else None

    async def save(self, order: Order, idempotency_key: str | None = None) -> None:
        pool = self._runtime.require_pool()
        async with pool.acquire() as connection, connection.transaction():
            current = await connection.fetchrow(
                "SELECT version, status FROM orders WHERE id = $1 FOR UPDATE", order.id
            )
            if current is None:
                event_name = "order.created"
                await connection.execute(
                    """
                    INSERT INTO orders(
                        id, customer_id, items, total, status, created_at, version, idempotency_key
                    ) VALUES($1, $2, $3::jsonb, $4, $5, $6, $7, $8)
                    """,
                    order.id,
                    order.customer_id,
                    json.dumps(order_payload(order)["items"]),
                    order.total,
                    order.status.value,
                    order.created_at,
                    order.version,
                    idempotency_key,
                )
            else:
                if order.version == current["version"] and order.status.value == current["status"]:
                    return
                if order.version != current["version"] + 1:
                    raise RuntimeError("Optimistic concurrency conflict")
                event_name = f"order.{order.status.value}"
                await connection.execute(
                    """
                    UPDATE orders
                    SET status = $2, version = $3
                    WHERE id = $1
                    """,
                    order.id,
                    order.status.value,
                    order.version,
                )
            await append_outbox(
                connection,
                EventEnvelope.create(event_name, order.id, {"order": order_payload(order)}),
            )

    @staticmethod
    def _from_row(row: asyncpg.Record) -> Order:
        return Order(
            id=row["id"],
            customer_id=row["customer_id"],
            items=tuple(
                OrderItem(item["sku"], item["quantity"]) for item in json_value(row["items"])
            ),
            total=row["total"],
            status=OrderStatus(row["status"]),
            created_at=row["created_at"],
            version=row["version"],
        )


class PostgresOrderReadModel:
    """Command-side apply is a no-op; RabbitMQ consumers update this projection."""

    def __init__(self, runtime: PostgresRuntime) -> None:
        self._runtime = runtime

    async def apply(self, event: OrderChanged) -> None:
        return None

    async def get(self, order_id: str) -> OrderView | None:
        async with self._runtime.require_pool().acquire() as connection:
            value = await connection.fetchval(
                "SELECT data FROM order_views WHERE id = $1", order_id
            )
        return self._view(json_value(value)) if value else None

    async def list(self) -> list[OrderView]:
        async with self._runtime.require_pool().acquire() as connection:
            rows = await connection.fetch(
                "SELECT data FROM order_views ORDER BY (data->>'created_at')::timestamptz"
            )
        return [self._view(json_value(row["data"])) for row in rows]

    async def project(self, connection: DbConnection, event: EventEnvelope) -> None:
        data = event.payload["order"]
        await connection.execute(
            """
            INSERT INTO order_views(id, data, projected_at)
            VALUES($1, $2::jsonb, NOW())
            ON CONFLICT (id) DO UPDATE
            SET data = EXCLUDED.data, projected_at = NOW()
            WHERE (order_views.data->>'version')::integer <=
                  (EXCLUDED.data->>'version')::integer
            """,
            data["id"],
            json.dumps(data),
        )

    @staticmethod
    def _view(data: dict[str, Any]) -> OrderView:
        return OrderView.from_order(order_from_payload(data))
