from fastapi import FastAPI

from services.shared.api import configure_logging, install_common_api_features

from .api.routes import build_router
from .application.handlers import OrderCommandHandler, OrderQueryHandler
from .infrastructure.memory import InMemoryOrderReadModel, InMemoryOrderWriteRepository


def create_app() -> FastAPI:
    configure_logging()
    app = FastAPI(title="order-service", version="1.0.0")
    write_repo = InMemoryOrderWriteRepository()
    read_model = InMemoryOrderReadModel()
    app.include_router(
        build_router(OrderCommandHandler(write_repo, read_model), OrderQueryHandler(read_model))
    )
    install_common_api_features(app)
    return app


app = create_app()
