from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from services.shared.api import configure_logging, install_common_api_features

from .api.routes import build_router
from .application.handlers import CheckoutSagaHandler, SagaQueryHandler
from .application.ports import CommerceGateway
from .config import Settings
from .infrastructure.http_gateway import HttpCommerceGateway
from .infrastructure.memory import InMemorySagaReadModel, InMemorySagaWriteRepository


def create_app(gateway: CommerceGateway | None = None) -> FastAPI:
    configure_logging()
    owned_gateway: HttpCommerceGateway | None = None
    if gateway is None:
        settings = Settings()
        owned_gateway = HttpCommerceGateway(
            settings.order_service_url,
            settings.inventory_service_url,
            settings.payment_service_url,
            settings.downstream_timeout_seconds,
        )
        gateway = owned_gateway

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        yield
        if owned_gateway is not None:
            await owned_gateway.close()

    app = FastAPI(title="saga-orchestrator", version="1.0.0", lifespan=lifespan)
    write_repo = InMemorySagaWriteRepository()
    read_model = InMemorySagaReadModel()
    app.include_router(
        build_router(
            CheckoutSagaHandler(write_repo, read_model, gateway), SagaQueryHandler(read_model)
        )
    )
    install_common_api_features(app)
    return app


app = create_app()
