from fastapi import FastAPI

from services.shared.api import configure_logging, install_common_api_features

from .api.routes import build_router
from .application.handlers import PaymentCommandHandler, PaymentQueryHandler
from .infrastructure.memory import InMemoryPaymentReadModel, InMemoryPaymentWriteRepository


def create_app() -> FastAPI:
    configure_logging()
    app = FastAPI(title="payment-service", version="1.0.0")
    write_repo = InMemoryPaymentWriteRepository()
    read_model = InMemoryPaymentReadModel()
    app.include_router(
        build_router(PaymentCommandHandler(write_repo, read_model), PaymentQueryHandler(read_model))
    )
    install_common_api_features(app)
    return app


app = create_app()
