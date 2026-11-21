from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from contextlib import suppress

import aio_pika
from aio_pika.abc import AbstractIncomingMessage, AbstractRobustConnection

from .events import EventEnvelope
from .postgres import DbConnection, PostgresRuntime, json_value

logger = logging.getLogger(__name__)
Projection = Callable[[DbConnection, EventEnvelope], Awaitable[None]]


class OutboxPublisher:
    """Publishes committed outbox rows with publisher confirms.

    A crash after publish but before marking a row can publish it again. That is intentional:
    delivery is at-least-once, and the consumer inbox removes duplicates.
    """

    def __init__(
        self,
        postgres: PostgresRuntime,
        rabbitmq_url: str,
        poll_seconds: float = 0.25,
    ) -> None:
        self._postgres = postgres
        self._url = rabbitmq_url
        self._poll_seconds = poll_seconds
        self._connection: AbstractRobustConnection | None = None
        self._task: asyncio.Task[None] | None = None
        self._stop = asyncio.Event()

    async def start(self) -> None:
        self._connection = await aio_pika.connect_robust(self._url)
        self._task = asyncio.create_task(self._run(), name="outbox-publisher")

    async def stop(self) -> None:
        self._stop.set()
        if self._task:
            self._task.cancel()
            with suppress(asyncio.CancelledError):
                await self._task
        if self._connection:
            await self._connection.close()

    async def _run(self) -> None:
        assert self._connection is not None
        channel = await self._connection.channel(publisher_confirms=True)
        exchange = await channel.declare_exchange(
            "domain.events", aio_pika.ExchangeType.TOPIC, durable=True
        )
        while not self._stop.is_set():
            try:
                published = await self._publish_batch(exchange)
            except Exception:
                logger.exception("Outbox publish cycle failed")
                published = False
            if not published:
                await asyncio.sleep(self._poll_seconds)

    async def _publish_batch(self, exchange: aio_pika.abc.AbstractExchange) -> bool:
        pool = self._postgres.require_pool()
        async with pool.acquire() as connection, connection.transaction():
            rows = await connection.fetch(
                """
                SELECT id, event_name, aggregate_id, payload, occurred_at
                FROM outbox_events
                WHERE published_at IS NULL
                ORDER BY occurred_at
                FOR UPDATE SKIP LOCKED
                LIMIT 100
                """
            )
            for row in rows:
                envelope = EventEnvelope(
                    row["id"],
                    row["event_name"],
                    row["aggregate_id"],
                    json_value(row["payload"]),
                    row["occurred_at"],
                )
                await exchange.publish(
                    aio_pika.Message(
                        body=envelope.to_json().encode(),
                        content_type="application/json",
                        delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                        message_id=envelope.id,
                    ),
                    routing_key=envelope.name,
                )
                await connection.execute(
                    """
                    UPDATE outbox_events
                    SET published_at = NOW(), attempts = attempts + 1
                    WHERE id = $1
                    """,
                    envelope.id,
                )
            return bool(rows)


class InboxProjectionConsumer:
    """Deduplicates an event and updates its projection in one DB transaction."""

    def __init__(
        self,
        postgres: PostgresRuntime,
        rabbitmq_url: str,
        queue_name: str,
        routing_key: str,
        projector: Projection,
    ) -> None:
        self._postgres = postgres
        self._url = rabbitmq_url
        self._queue_name = queue_name
        self._routing_key = routing_key
        self._projector = projector
        self._connection: AbstractRobustConnection | None = None

    async def start(self) -> None:
        self._connection = await aio_pika.connect_robust(self._url)
        channel = await self._connection.channel()
        await channel.set_qos(prefetch_count=50)
        exchange = await channel.declare_exchange(
            "domain.events", aio_pika.ExchangeType.TOPIC, durable=True
        )
        queue = await channel.declare_queue(self._queue_name, durable=True)
        await queue.bind(exchange, routing_key=self._routing_key)
        await queue.consume(self._handle)

    async def stop(self) -> None:
        if self._connection:
            await self._connection.close()

    async def _handle(self, message: AbstractIncomingMessage) -> None:
        envelope = EventEnvelope.from_json(message.body)
        try:
            pool = self._postgres.require_pool()
            async with pool.acquire() as connection, connection.transaction():
                inserted = await connection.fetchval(
                    """
                    INSERT INTO inbox_events(event_id, event_name)
                    VALUES($1, $2)
                    ON CONFLICT (event_id) DO NOTHING
                    RETURNING event_id
                    """,
                    envelope.id,
                    envelope.name,
                )
                if inserted is not None:
                    await self._projector(connection, envelope)
            await message.ack()
        except Exception:
            logger.exception("Projection failed for event_id=%s", envelope.id)
            await message.nack(requeue=True)
