from fastapi import FastAPI

from services.shared.api import configure_logging, install_common_api_features

from .api.routes import build_router
from .application.handlers import InventoryCommandHandler, InventoryQueryHandler
from .infrastructure.memory import InMemoryInventoryReadModel, InMemoryInventoryWriteRepository


def create_app(initial_stock: dict[str, int] | None = None) -> FastAPI:
    configure_logging()
    app = FastAPI(title="inventory-service", version="1.0.0")
    write_repo = InMemoryInventoryWriteRepository(initial_stock)
    read_model = InMemoryInventoryReadModel(initial_stock)
    app.include_router(
        build_router(
            InventoryCommandHandler(write_repo, read_model), InventoryQueryHandler(read_model)
        )
    )
    install_common_api_features(app)
    return app


app = create_app()
