from __future__ import annotations

import json
from typing import Any

import asyncpg

from services.shared.events import EventEnvelope
from services.shared.postgres import DbConnection, PostgresRuntime, append_outbox, json_value

from ..application.handlers import ReservationNotFoundError
from ..domain.events import InventoryChanged
from ..domain.models import (
    InsufficientStockError,
    Reservation,
    ReservationItem,
    ReservationStatus,
    StockItem,
)

INVENTORY_SCHEMA = """
CREATE TABLE IF NOT EXISTS inventory_stock (
    sku TEXT PRIMARY KEY,
    on_hand INTEGER NOT NULL CHECK (on_hand >= 0),
    reserved INTEGER NOT NULL DEFAULT 0 CHECK (reserved >= 0 AND reserved <= on_hand)
);

CREATE TABLE IF NOT EXISTS reservations (
    id TEXT PRIMARY KEY,
    order_id TEXT NOT NULL,
    items JSONB NOT NULL,
    status TEXT NOT NULL,
    idempotency_key TEXT UNIQUE NOT NULL
);

CREATE TABLE IF NOT EXISTS stock_views (
    sku TEXT PRIMARY KEY,
    data JSONB NOT NULL,
    projected_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS reservation_views (
    id TEXT PRIMARY KEY,
    data JSONB NOT NULL,
    projected_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""

DEFAULT_STOCK = {"LAPTOP": 10, "HEADPHONES": 25, "KEYBOARD": 15}


def item_payload(item: ReservationItem) -> dict[str, Any]:
    return {"sku": item.sku, "quantity": item.quantity}


def reservation_payload(reservation: Reservation) -> dict[str, Any]:
    return {
        "id": reservation.id,
        "order_id": reservation.order_id,
        "items": [item_payload(item) for item in reservation.items],
        "status": reservation.status.value,
    }


def reservation_from_payload(data: dict[str, Any]) -> Reservation:
    return Reservation(
        data["id"],
        data["order_id"],
        tuple(ReservationItem(item["sku"], item["quantity"]) for item in data["items"]),
        ReservationStatus(data["status"]),
    )


def stock_payload(stock: StockItem) -> dict[str, Any]:
    return {
        "sku": stock.sku,
        "on_hand": stock.on_hand,
        "reserved": stock.reserved,
        "available": stock.available,
    }


class PostgresInventoryWriteRepository:
    def __init__(self, runtime: PostgresRuntime) -> None:
        self._runtime = runtime

    async def initialize(self) -> None:
        async with self._runtime.require_pool().acquire() as connection, connection.transaction():
            for sku, on_hand in DEFAULT_STOCK.items():
                await connection.execute(
                    """
                    INSERT INTO inventory_stock(sku, on_hand) VALUES($1, $2)
                    ON CONFLICT (sku) DO NOTHING
                    """,
                    sku,
                    on_hand,
                )
                await connection.execute(
                    """
                    INSERT INTO stock_views(sku, data)
                    VALUES($1, $2::jsonb)
                    ON CONFLICT (sku) DO NOTHING
                    """,
                    sku,
                    json.dumps(stock_payload(StockItem(sku, on_hand))),
                )

    async def reserve(
        self,
        reservation_id: str,
        order_id: str,
        items: tuple[ReservationItem, ...],
        idempotency_key: str,
    ) -> InventoryChanged:
        pool = self._runtime.require_pool()
        async with pool.acquire() as connection, connection.transaction():
            previous = await connection.fetchrow(
                "SELECT * FROM reservations WHERE idempotency_key = $1", idempotency_key
            )
            if previous:
                reservation = self._reservation_from_row(previous)
                return await self._event(connection, reservation, "inventory.reservation_replayed")

            requested_by_sku: dict[str, int] = {}
            for item in items:
                if item.quantity <= 0:
                    raise ValueError("Reservation quantity must be positive")
                requested_by_sku[item.sku] = requested_by_sku.get(item.sku, 0) + item.quantity

            rows = await connection.fetch(
                "SELECT * FROM inventory_stock WHERE sku = ANY($1::text[]) FOR UPDATE",
                list(requested_by_sku),
            )
            stocks = {row["sku"]: row for row in rows}
            for sku, quantity in requested_by_sku.items():
                row = stocks.get(sku)
                available = row["on_hand"] - row["reserved"] if row else 0
                if available < quantity:
                    raise InsufficientStockError(sku, quantity, available)

            reservation = Reservation(reservation_id, order_id, items)
            for sku, quantity in requested_by_sku.items():
                await connection.execute(
                    "UPDATE inventory_stock SET reserved = reserved + $2 WHERE sku = $1",
                    sku,
                    quantity,
                )
            await connection.execute(
                """
                INSERT INTO reservations(id, order_id, items, status, idempotency_key)
                VALUES($1, $2, $3::jsonb, $4, $5)
                """,
                reservation.id,
                reservation.order_id,
                json.dumps([item_payload(item) for item in reservation.items]),
                reservation.status.value,
                idempotency_key,
            )
            event = await self._event(connection, reservation, "inventory.reserved")
            await append_outbox(connection, self._envelope(event))
            return event

    async def release(self, reservation_id: str) -> InventoryChanged:
        pool = self._runtime.require_pool()
        async with pool.acquire() as connection, connection.transaction():
            row = await connection.fetchrow(
                "SELECT * FROM reservations WHERE id = $1 FOR UPDATE", reservation_id
            )
            if row is None:
                raise ReservationNotFoundError(reservation_id)
            reservation = self._reservation_from_row(row)
            if reservation.status == ReservationStatus.RELEASED:
                return await self._event(connection, reservation, "inventory.release_replayed")
            for item in reservation.items:
                await connection.execute(
                    "UPDATE inventory_stock SET reserved = reserved - $2 WHERE sku = $1",
                    item.sku,
                    item.quantity,
                )
            released = Reservation(
                reservation.id,
                reservation.order_id,
                reservation.items,
                ReservationStatus.RELEASED,
            )
            await connection.execute(
                "UPDATE reservations SET status = $2 WHERE id = $1",
                released.id,
                released.status.value,
            )
            event = await self._event(connection, released, "inventory.released")
            await append_outbox(connection, self._envelope(event))
            return event

    async def _event(
        self, connection: DbConnection, reservation: Reservation, name: str
    ) -> InventoryChanged:
        rows = await connection.fetch("SELECT * FROM inventory_stock ORDER BY sku")
        stocks = tuple(StockItem(row["sku"], row["on_hand"], row["reserved"]) for row in rows)
        return InventoryChanged(stocks, reservation, name)

    @staticmethod
    def _envelope(event: InventoryChanged) -> EventEnvelope:
        return EventEnvelope.create(
            event.event_name,
            event.reservation.id,
            {
                "reservation": reservation_payload(event.reservation),
                "stocks": [stock_payload(stock) for stock in event.stocks],
            },
        )

    @staticmethod
    def _reservation_from_row(row: asyncpg.Record) -> Reservation:
        return Reservation(
            row["id"],
            row["order_id"],
            tuple(
                ReservationItem(item["sku"], item["quantity"]) for item in json_value(row["items"])
            ),
            ReservationStatus(row["status"]),
        )


class PostgresInventoryReadModel:
    def __init__(self, runtime: PostgresRuntime) -> None:
        self._runtime = runtime

    async def apply(self, event: InventoryChanged) -> None:
        return None

    async def get_reservation(self, reservation_id: str) -> Reservation | None:
        async with self._runtime.require_pool().acquire() as connection:
            value = await connection.fetchval(
                "SELECT data FROM reservation_views WHERE id = $1", reservation_id
            )
        return reservation_from_payload(json_value(value)) if value else None

    async def list_stock(self) -> list[StockItem]:
        async with self._runtime.require_pool().acquire() as connection:
            rows = await connection.fetch("SELECT data FROM stock_views ORDER BY sku")
        return [
            StockItem(data["sku"], data["on_hand"], data["reserved"])
            for row in rows
            for data in [json_value(row["data"])]
        ]

    async def project(self, connection: DbConnection, event: EventEnvelope) -> None:
        reservation = event.payload["reservation"]
        await connection.execute(
            """
            INSERT INTO reservation_views(id, data, projected_at)
            VALUES($1, $2::jsonb, NOW())
            ON CONFLICT (id) DO UPDATE SET data = EXCLUDED.data, projected_at = NOW()
            """,
            reservation["id"],
            json.dumps(reservation),
        )
        for stock in event.payload["stocks"]:
            await connection.execute(
                """
                INSERT INTO stock_views(sku, data, projected_at)
                VALUES($1, $2::jsonb, NOW())
                ON CONFLICT (sku) DO UPDATE SET data = EXCLUDED.data, projected_at = NOW()
                """,
                stock["sku"],
                json.dumps(stock),
            )
