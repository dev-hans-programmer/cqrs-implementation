# 5. Asynchronous Read Projections

## Flow

In PostgreSQL mode, command handlers no longer update their query models directly. Their
`read_model.apply()` is deliberately a no-op. The outbox and RabbitMQ consumer update read tables:

```text
Command response -> outbox -> RabbitMQ -> inbox -> projection
```

Query handlers read only projection tables such as `order_views`, `stock_views`,
`payment_views`, and `saga_views`.

## Eventual consistency

A command can return before its projection is updated. A subsequent GET may briefly return old
data or `404`. Clients can:

- use the command response as immediate confirmation;
- retry a query with bounded backoff;
- display a pending state;
- wait for a version or event position;
- receive a push notification when processing finishes.

Projection updates are designed to tolerate out-of-order older events. Order views compare
aggregate versions; Saga views compare timeline lengths. The inbox prevents duplicate application.

## Rebuilding projections

The current broker is not an indefinite event store, so rebuilding requires retained events or a
snapshot/export from write models. A mature platform defines a replay process, projection version,
shadow table, validation step, and atomic cutover.

