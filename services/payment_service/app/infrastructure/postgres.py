from __future__ import annotations

import json
from decimal import Decimal
from typing import Any

import asyncpg

from services.shared.events import EventEnvelope
from services.shared.postgres import DbConnection, PostgresRuntime, append_outbox, json_value

from ..application.handlers import PaymentNotFoundError
from ..domain.events import PaymentChanged
from ..domain.models import Payment, PaymentStatus

PAYMENT_SCHEMA = """
CREATE TABLE IF NOT EXISTS payments (
    id TEXT PRIMARY KEY,
    order_id TEXT NOT NULL,
    amount NUMERIC(12, 2) NOT NULL,
    status TEXT NOT NULL,
    decline_reason TEXT,
    idempotency_key TEXT UNIQUE NOT NULL
);

CREATE TABLE IF NOT EXISTS payment_views (
    id TEXT PRIMARY KEY,
    data JSONB NOT NULL,
    projected_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""


def payment_payload(payment: Payment) -> dict[str, Any]:
    return {
        "id": payment.id,
        "order_id": payment.order_id,
        "amount": str(payment.amount),
        "status": payment.status.value,
        "decline_reason": payment.decline_reason,
    }


def payment_from_payload(data: dict[str, Any]) -> Payment:
    return Payment(
        data["id"],
        data["order_id"],
        Decimal(data["amount"]),
        PaymentStatus(data["status"]),
        data.get("decline_reason"),
    )


class PostgresPaymentWriteRepository:
    def __init__(self, runtime: PostgresRuntime) -> None:
        self._runtime = runtime

    async def authorize(
        self,
        payment_id: str,
        order_id: str,
        amount: Decimal,
        payment_method_token: str,
        idempotency_key: str,
    ) -> PaymentChanged:
        pool = self._runtime.require_pool()
        async with pool.acquire() as connection, connection.transaction():
            previous = await connection.fetchrow(
                "SELECT * FROM payments WHERE idempotency_key = $1", idempotency_key
            )
            if previous:
                return PaymentChanged(self._from_row(previous), "payment.authorization_replayed")
            if amount <= 0:
                raise ValueError("Payment amount must be positive")
            if payment_method_token == "tok_fail":
                payment = Payment(
                    payment_id, order_id, amount, PaymentStatus.DECLINED, "Card was declined"
                )
                event_name = "payment.declined"
            else:
                payment = Payment(payment_id, order_id, amount, PaymentStatus.AUTHORIZED)
                event_name = "payment.authorized"
            await connection.execute(
                """
                INSERT INTO payments(
                    id, order_id, amount, status, decline_reason, idempotency_key
                ) VALUES($1, $2, $3, $4, $5, $6)
                """,
                payment.id,
                payment.order_id,
                payment.amount,
                payment.status.value,
                payment.decline_reason,
                idempotency_key,
            )
            event = PaymentChanged(payment, event_name)
            await append_outbox(connection, self._envelope(event))
            return event

    async def refund(self, payment_id: str) -> PaymentChanged:
        pool = self._runtime.require_pool()
        async with pool.acquire() as connection, connection.transaction():
            row = await connection.fetchrow(
                "SELECT * FROM payments WHERE id = $1 FOR UPDATE", payment_id
            )
            if row is None:
                raise PaymentNotFoundError(payment_id)
            payment = self._from_row(row)
            refunded = payment.refund()
            if refunded == payment:
                return PaymentChanged(refunded, "payment.refund_replayed")
            await connection.execute(
                "UPDATE payments SET status = $2 WHERE id = $1",
                refunded.id,
                refunded.status.value,
            )
            event = PaymentChanged(refunded, "payment.refunded")
            await append_outbox(connection, self._envelope(event))
            return event

    @staticmethod
    def _envelope(event: PaymentChanged) -> EventEnvelope:
        return EventEnvelope.create(
            event.event_name,
            event.payment.id,
            {"payment": payment_payload(event.payment)},
        )

    @staticmethod
    def _from_row(row: asyncpg.Record) -> Payment:
        return Payment(
            row["id"],
            row["order_id"],
            row["amount"],
            PaymentStatus(row["status"]),
            row["decline_reason"],
        )


class PostgresPaymentReadModel:
    def __init__(self, runtime: PostgresRuntime) -> None:
        self._runtime = runtime

    async def apply(self, event: PaymentChanged) -> None:
        return None

    async def get(self, payment_id: str) -> Payment | None:
        async with self._runtime.require_pool().acquire() as connection:
            value = await connection.fetchval(
                "SELECT data FROM payment_views WHERE id = $1", payment_id
            )
        return payment_from_payload(json_value(value)) if value else None

    async def project(self, connection: DbConnection, event: EventEnvelope) -> None:
        data = event.payload["payment"]
        await connection.execute(
            """
            INSERT INTO payment_views(id, data, projected_at)
            VALUES($1, $2::jsonb, NOW())
            ON CONFLICT (id) DO UPDATE SET data = EXCLUDED.data, projected_at = NOW()
            """,
            data["id"],
            json.dumps(data),
        )
