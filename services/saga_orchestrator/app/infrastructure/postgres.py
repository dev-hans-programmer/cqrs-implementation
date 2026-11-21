from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal
from typing import Any

from services.shared.events import EventEnvelope
from services.shared.postgres import DbConnection, PostgresRuntime, append_outbox, json_value

from ..domain.events import SagaChanged
from ..domain.models import (
    CheckoutItem,
    CheckoutSaga,
    SagaStatus,
    SagaStep,
    StepStatus,
)

SAGA_SCHEMA = """
CREATE TABLE IF NOT EXISTS checkout_sagas (
    id TEXT PRIMARY KEY,
    idempotency_key TEXT UNIQUE NOT NULL,
    status TEXT NOT NULL,
    data JSONB NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    recovery_lease_until TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_saga_recovery
    ON checkout_sagas(status, updated_at)
    WHERE status IN ('running', 'compensating');

CREATE TABLE IF NOT EXISTS saga_views (
    id TEXT PRIMARY KEY,
    data JSONB NOT NULL,
    projected_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""


def saga_payload(saga: CheckoutSaga, include_payment_token: bool = True) -> dict[str, Any]:
    data: dict[str, Any] = {
        "id": saga.id,
        "idempotency_key": saga.idempotency_key,
        "order_id": saga.order_id,
        "reservation_id": saga.reservation_id,
        "payment_id": saga.payment_id,
        "customer_id": saga.customer_id,
        "items": [{"sku": item.sku, "quantity": item.quantity} for item in saga.items],
        "amount": str(saga.amount),
        "status": saga.status.value,
        "steps": [
            {
                "name": step.name,
                "status": step.status.value,
                "occurred_at": step.occurred_at.isoformat(),
                "detail": step.detail,
            }
            for step in saga.steps
        ],
        "failure_reason": saga.failure_reason,
    }
    if include_payment_token:
        # This is a provider token/reference, never raw card data. A production system may
        # persist only a vault reference and resolve it during recovery.
        data["payment_method_token"] = saga.payment_method_token
    return data


def saga_from_payload(data: dict[str, Any]) -> CheckoutSaga:
    return CheckoutSaga(
        id=data["id"],
        idempotency_key=data["idempotency_key"],
        order_id=data["order_id"],
        reservation_id=data["reservation_id"],
        payment_id=data["payment_id"],
        customer_id=data["customer_id"],
        items=tuple(CheckoutItem(item["sku"], item["quantity"]) for item in data["items"]),
        amount=Decimal(data["amount"]),
        payment_method_token=data.get("payment_method_token", ""),
        status=SagaStatus(data["status"]),
        steps=tuple(
            SagaStep(
                step["name"],
                StepStatus(step["status"]),
                datetime.fromisoformat(step["occurred_at"]),
                step.get("detail"),
            )
            for step in data["steps"]
        ),
        failure_reason=data.get("failure_reason"),
    )


class PostgresSagaWriteRepository:
    def __init__(self, runtime: PostgresRuntime) -> None:
        self._runtime = runtime

    async def get_by_idempotency_key(self, key: str) -> CheckoutSaga | None:
        async with self._runtime.require_pool().acquire() as connection:
            value = await connection.fetchval(
                "SELECT data FROM checkout_sagas WHERE idempotency_key = $1", key
            )
        return saga_from_payload(json_value(value)) if value else None

    async def save(self, saga: CheckoutSaga) -> None:
        pool = self._runtime.require_pool()
        write_data = saga_payload(saga)
        public_data = saga_payload(saga, include_payment_token=False)
        async with pool.acquire() as connection, connection.transaction():
            await connection.execute(
                """
                INSERT INTO checkout_sagas(id, idempotency_key, status, data, updated_at)
                VALUES($1, $2, $3, $4::jsonb, NOW())
                ON CONFLICT (id) DO UPDATE
                SET status = EXCLUDED.status,
                    data = EXCLUDED.data,
                    updated_at = NOW()
                """,
                saga.id,
                saga.idempotency_key,
                saga.status.value,
                json.dumps(write_data),
            )
            await append_outbox(
                connection,
                EventEnvelope.create("saga.changed", saga.id, {"saga": public_data}),
            )

    async def list_recoverable(self, stale_after_seconds: float) -> list[CheckoutSaga]:
        async with self._runtime.require_pool().acquire() as connection:
            rows = await connection.fetch(
                """
                WITH candidates AS (
                    SELECT id
                    FROM checkout_sagas
                    WHERE status IN ('running', 'compensating')
                      AND updated_at < NOW() - ($1 * INTERVAL '1 second')
                      AND (
                          recovery_lease_until IS NULL OR recovery_lease_until < NOW()
                      )
                    ORDER BY updated_at
                    FOR UPDATE SKIP LOCKED
                    LIMIT 50
                )
                UPDATE checkout_sagas AS saga
                SET recovery_lease_until = NOW() + INTERVAL '30 seconds'
                FROM candidates
                WHERE saga.id = candidates.id
                RETURNING saga.data
                """,
                stale_after_seconds,
            )
        return [saga_from_payload(json_value(row["data"])) for row in rows]


class PostgresSagaReadModel:
    def __init__(self, runtime: PostgresRuntime) -> None:
        self._runtime = runtime

    async def apply(self, event: SagaChanged) -> None:
        return None

    async def get(self, saga_id: str) -> CheckoutSaga | None:
        async with self._runtime.require_pool().acquire() as connection:
            value = await connection.fetchval("SELECT data FROM saga_views WHERE id = $1", saga_id)
        return saga_from_payload(json_value(value)) if value else None

    async def project(self, connection: DbConnection, event: EventEnvelope) -> None:
        data = event.payload["saga"]
        await connection.execute(
            """
            INSERT INTO saga_views(id, data, projected_at)
            VALUES($1, $2::jsonb, NOW())
            ON CONFLICT (id) DO UPDATE
            SET data = EXCLUDED.data, projected_at = NOW()
            WHERE jsonb_array_length(saga_views.data->'steps') <=
                  jsonb_array_length(EXCLUDED.data->'steps')
            """,
            data["id"],
            json.dumps(data),
        )
