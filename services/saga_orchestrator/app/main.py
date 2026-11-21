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
from .application.handlers import CheckoutSagaHandler, SagaQueryHandler
from .application.ports import CommerceGateway, SagaReadModel, SagaWriteRepository
from .config import Settings
from .infrastructure.http_gateway import HttpCommerceGateway
from .infrastructure.memory import InMemorySagaReadModel, InMemorySagaWriteRepository
from .infrastructure.postgres import (
    SAGA_SCHEMA,
    PostgresSagaReadModel,
    PostgresSagaWriteRepository,
)
from .infrastructure.recovery import SagaRecoveryWorker


def create_app(
    gateway: CommerceGateway | None = None,
    platform: PlatformSettings | None = None,
    settings: Settings | None = None,
) -> FastAPI:
    configure_logging()
    platform = platform or PlatformSettings()
    settings = settings or Settings()
    owned_gateway: HttpCommerceGateway | None = None
    if gateway is None:
        owned_gateway = HttpCommerceGateway(
            settings.order_service_url,
            settings.inventory_service_url,
            settings.payment_service_url,
            settings.downstream_timeout_seconds,
            settings.downstream_max_attempts,
            settings.retry_base_delay_seconds,
            settings.circuit_breaker_failure_threshold,
            settings.circuit_breaker_recovery_seconds,
        )
        gateway = owned_gateway

    publisher: OutboxPublisher | None = None
    consumer: InboxProjectionConsumer | None = None
    runtime: PostgresRuntime | None = None
    recovery: SagaRecoveryWorker | None = None

    write_repo: SagaWriteRepository
    read_model: SagaReadModel
    if platform.uses_postgres:
        if not platform.database_url or not platform.rabbitmq_url:
            raise ValueError("PostgreSQL mode requires DATABASE_URL and RABBITMQ_URL")
        runtime = PostgresRuntime(platform.database_url)
        write_repo = PostgresSagaWriteRepository(runtime)
        read_model = PostgresSagaReadModel(runtime)
        publisher = OutboxPublisher(runtime, platform.rabbitmq_url, platform.outbox_poll_seconds)
        consumer = InboxProjectionConsumer(
            runtime, platform.rabbitmq_url, "saga.projection", "saga.*", read_model.project
        )
    else:
        write_repo = InMemorySagaWriteRepository()
        read_model = InMemorySagaReadModel()

    command_handler = CheckoutSagaHandler(write_repo, read_model, gateway)
    if platform.uses_postgres:
        recovery = SagaRecoveryWorker(
            write_repo,
            command_handler,
            settings.saga_recovery_poll_seconds,
            settings.saga_stale_after_seconds,
        )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if runtime and publisher and consumer:
            await runtime.connect(SAGA_SCHEMA)
            await consumer.start()
            await publisher.start()
        if recovery:
            await recovery.start()
        try:
            yield
        finally:
            if recovery:
                await recovery.stop()
            if publisher:
                await publisher.stop()
            if consumer:
                await consumer.stop()
            if runtime:
                await runtime.close()
            if owned_gateway is not None:
                await owned_gateway.close()
            await close_common_api_features(app)

    app = FastAPI(title="saga-orchestrator", version="1.0.0", lifespan=lifespan)
    app.include_router(build_router(command_handler, SagaQueryHandler(read_model)))
    install_common_api_features(app, platform)
    return app


app = create_app()
