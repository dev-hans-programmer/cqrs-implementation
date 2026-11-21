from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Callable
from contextvars import ContextVar
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

correlation_id: ContextVar[str] = ContextVar("correlation_id", default="-")


def configure_logging() -> None:
    """Use a container-friendly format and include correlation IDs in every record."""

    class CorrelationFilter(logging.Filter):
        def filter(self, record: logging.LogRecord) -> bool:
            record.correlation_id = correlation_id.get()
            return True

    handler = logging.StreamHandler()
    handler.addFilter(CorrelationFilter())
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s %(levelname)s %(name)s correlation_id=%(correlation_id)s %(message)s"
        )
    )
    logging.basicConfig(level=logging.INFO, handlers=[handler], force=True)


def install_common_api_features(app: FastAPI) -> None:
    @app.middleware("http")
    async def request_context(
        request: Request,
        call_next: Callable[[Request], Awaitable[JSONResponse]],
    ) -> JSONResponse:
        request_id = request.headers.get("X-Correlation-ID", str(uuid4()))
        token = correlation_id.set(request_id)
        started = time.perf_counter()
        try:
            response = await call_next(request)
            response.headers["X-Correlation-ID"] = request_id
            response.headers["X-Process-Time"] = f"{time.perf_counter() - started:.6f}"
            return response
        finally:
            correlation_id.reset(token)

    @app.get("/health", tags=["platform"])
    async def health() -> dict[str, str]:
        return {"status": "ok", "service": app.title}
