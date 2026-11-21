from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from services.shared.api import (
    close_common_api_features,
    configure_logging,
    install_common_api_features,
)
from services.shared.config import PlatformSettings
from services.shared.messaging import InboxProjectionConsumer, OutboxPublisher
from services.shared.postgres import PostgresRuntime

from .api.routes import build_router
from .application.handlers import OrderCommandHandler, OrderQueryHandler
from .application.ports import OrderReadModel, OrderWriteRepository
from .infrastructure.memory import InMemoryOrderReadModel, InMemoryOrderWriteRepository
from .infrastructure.postgres import (
    ORDER_SCHEMA,
    PostgresOrderReadModel,
    PostgresOrderWriteRepository,
)


def create_app(platform: PlatformSettings | None = None) -> FastAPI:
    configure_logging()
    platform = platform or PlatformSettings()
    publisher: OutboxPublisher | None = None
    consumer: InboxProjectionConsumer | None = None
    runtime: PostgresRuntime | None = None

    write_repo: OrderWriteRepository
    read_model: OrderReadModel
    if platform.uses_postgres:
        if not platform.database_url or not platform.rabbitmq_url:
            raise ValueError("PostgreSQL mode requires DATABASE_URL and RABBITMQ_URL")
        runtime = PostgresRuntime(platform.database_url)
        write_repo = PostgresOrderWriteRepository(runtime)
        read_model = PostgresOrderReadModel(runtime)
        publisher = OutboxPublisher(runtime, platform.rabbitmq_url, platform.outbox_poll_seconds)
        consumer = InboxProjectionConsumer(
            runtime, platform.rabbitmq_url, "order.projection", "order.*", read_model.project
        )
    else:
        write_repo = InMemoryOrderWriteRepository()
        read_model = InMemoryOrderReadModel()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if runtime and publisher and consumer:
            await runtime.connect(ORDER_SCHEMA)
            await consumer.start()
            await publisher.start()
        try:
            yield
        finally:
            if publisher:
                await publisher.stop()
            if consumer:
                await consumer.stop()
            if runtime:
                await runtime.close()
            await close_common_api_features(app)

    app = FastAPI(title="order-service", version="1.0.0", lifespan=lifespan)
    app.include_router(
        build_router(OrderCommandHandler(write_repo, read_model), OrderQueryHandler(read_model))
    )
    install_common_api_features(app, platform)
    return app


app = create_app()
