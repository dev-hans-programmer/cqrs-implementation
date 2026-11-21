# 1. PostgreSQL Write Repositories

## Why

In-memory state disappears on restart and cannot be shared by replicas. Each bounded context now
has a PostgreSQL implementation of its application-owned repository protocol:

- `order_service/app/infrastructure/postgres.py`
- `inventory_service/app/infrastructure/postgres.py`
- `payment_service/app/infrastructure/postgres.py`
- `saga_orchestrator/app/infrastructure/postgres.py`

Docker Compose gives every service its own database container. Services never query another
service's tables.

## Runtime selection

```text
PERSISTENCE_BACKEND=memory    -> in-memory repository + synchronous projection
PERSISTENCE_BACKEND=postgres  -> PostgreSQL repository + asynchronous projection
```

`main.py` is the composition root that selects the implementation. Application handlers and
domain models remain unchanged because they depend on protocols, not asyncpg.

## Transaction boundaries

Order writes use optimistic versions. Inventory uses `SELECT ... FOR UPDATE` so checking available
stock and increasing reserved stock are atomic. Payments use a unique idempotency key. Saga state
stores every durable workflow step.

Each write transaction also inserts an outbox event. A business update is never committed without
the event needed by its projection.

## Schema management

`PostgresRuntime.connect()` installs the common delivery tables and each repository supplies its
service schema. This is convenient for the example. A real deployment should use reviewed,
versioned Alembic/Flyway migrations run separately from application startup.

## Inspect it

```bash
docker compose exec order-db psql -U app -d orders -c 'TABLE orders;'
docker compose exec inventory-db psql -U app -d inventory -c 'TABLE inventory_stock;'
docker compose exec saga-db psql -U app -d sagas -c 'TABLE checkout_sagas;'
```

Do not introduce cross-database joins. Cross-service information belongs in APIs, events, or local
projections.

