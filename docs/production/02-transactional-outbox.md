# 2. Transactional Outbox

## The dual-write problem

This is unsafe:

```text
1. Commit order to PostgreSQL
2. Publish OrderCreated to RabbitMQ
```

A crash between the two steps creates an order whose event is permanently lost. Reversing the
steps can publish an event for a transaction that later rolls back.

## Implementation

Every PostgreSQL repository calls `append_outbox()` using the same asyncpg connection and
transaction as its business write:

```text
BEGIN
  update aggregate
  insert outbox event
COMMIT
```

`services/shared/messaging.py::OutboxPublisher` polls committed, unpublished rows using
`FOR UPDATE SKIP LOCKED`. Multiple publisher replicas can work without selecting the same row.
Messages are persistent and RabbitMQ publisher confirms are enabled. A row is marked published
only after confirmation.

## Delivery semantics

A process can crash after RabbitMQ confirms but before PostgreSQL records `published_at`. The row
will be published again. Therefore the outbox guarantees at-least-once delivery, not exactly once.
The inbox handles duplicates.

## Inspect it

```bash
docker compose exec order-db psql -U app -d orders -c \
  'SELECT id,event_name,published_at,attempts FROM outbox_events ORDER BY occurred_at DESC;'
```

Production additions commonly include outbox retention, partitioning, unpublished-event alerts,
publish-latency metrics, and a dead-letter policy for permanently invalid events.

