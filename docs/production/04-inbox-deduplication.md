# 4. Inbox and Deduplication

## Why consumers must be idempotent

At-least-once delivery means the same event may arrive repeatedly. Updating a counter or sending a
notification twice could corrupt business behavior.

`InboxProjectionConsumer` starts one database transaction and performs:

```text
BEGIN
  INSERT inbox_events(event_id) ON CONFLICT DO NOTHING
  if inserted: update projection
COMMIT
ACK RabbitMQ message
```

The unique `event_id` is the deduplication boundary. If it already exists, the projection is not
applied again. The inbox record and projection update commit together, so neither can exist
without the other.

## Failure cases

| Failure point | Result |
|---|---|
| Before transaction commit | Transaction rolls back; message is redelivered |
| After commit, before ACK | Message is redelivered; inbox identifies the duplicate |
| Duplicate from outbox publisher | Inbox ignores it |
| Projection code raises | Transaction rolls back and message is requeued |

## Inspect it

```bash
docker compose exec order-db psql -U app -d orders -c \
  'SELECT * FROM inbox_events ORDER BY processed_at DESC;'
```

Inbox retention must exceed the maximum broker replay horizon. Deleting inbox IDs too soon can
allow an old replay to be processed again.

