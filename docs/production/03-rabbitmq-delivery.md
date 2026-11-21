# 3. RabbitMQ Event Delivery

## Topology

The shared publisher declares one durable topic exchange:

```text
exchange: domain.events
```

Each service owns a durable projection queue and binding:

| Queue | Binding |
|---|---|
| `order.projection` | `order.*` |
| `inventory.projection` | `inventory.*` |
| `payment.projection` | `payment.*` |
| `saga.projection` | `saga.*` |

Events use `EventEnvelope`, which carries an immutable event ID, name, aggregate ID, payload, and
occurrence time. Domain objects are serialized at the infrastructure boundary rather than being
placed directly on the wire.

## Reliability choices

- exchange, queues, and messages are durable;
- publisher confirms prevent premature outbox completion;
- robust aio-pika connections reconnect after broker interruptions;
- consumer prefetch is bounded at 50;
- handler failures reject and requeue the message;
- correlation IDs continue across HTTP, while event IDs identify broker deliveries.

Open `http://localhost:15672` and inspect the exchange, bindings, queue depth, and delivery rates.

## Production additions

Define schema compatibility rules, dead-letter exchanges, bounded redelivery, poison-message
alerts, queue ownership, retention limits, and broker clustering. Kafka could replace RabbitMQ;
the outbox/inbox semantics remain the same, while partitioning and consumer-group behavior differ.

