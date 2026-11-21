from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Callable
from contextvars import ContextVar
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
from prometheus_client import CollectorRegistry, Counter, Histogram, generate_latest

from .config import PlatformSettings
from .observability import configure_tracing
from .rate_limit import RedisTokenBucket

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


def install_common_api_features(app: FastAPI, settings: PlatformSettings | None = None) -> None:
    settings = settings or PlatformSettings()
    registry = CollectorRegistry()
    request_count = Counter(
        "http_requests_total",
        "HTTP requests received",
        ("service", "method", "path", "status"),
        registry=registry,
    )
    request_duration = Histogram(
        "http_request_duration_seconds",
        "HTTP request duration",
        ("service", "method", "path"),
        registry=registry,
    )
    rate_limiter = (
        RedisTokenBucket(
            settings.redis_url,
            settings.rate_limit_capacity,
            settings.rate_limit_refill_per_second,
        )
        if settings.rate_limit_enabled
        else None
    )
    app.state.rate_limiter = rate_limiter

    if settings.otel_enabled:
        configure_tracing(app, app.title, settings.otel_exporter_otlp_endpoint)

    @app.middleware("http")
    async def request_context(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        request_id = request.headers.get("X-Correlation-ID", str(uuid4()))
        token = correlation_id.set(request_id)
        started = time.perf_counter()
        try:
            if rate_limiter is not None and request.url.path not in {"/health", "/metrics"}:
                client_key = request.headers.get(
                    "X-Client-ID", request.client.host if request.client else "unknown"
                )
                try:
                    decision = await rate_limiter.acquire(f"{app.title}:{client_key}")
                except Exception:
                    # Rate limiting is fail-open: a Redis incident must not become a total outage.
                    logging.getLogger(__name__).exception("Rate limiter unavailable")
                else:
                    if not decision.allowed:
                        return JSONResponse(
                            {"detail": "Rate limit exceeded"},
                            status_code=429,
                            headers={
                                "X-RateLimit-Limit": str(rate_limiter.capacity),
                                "X-RateLimit-Remaining": str(decision.remaining),
                                "Retry-After": "1",
                            },
                        )
            response = await call_next(request)
            route = request.scope.get("route")
            path = getattr(route, "path", request.url.path)
            elapsed = time.perf_counter() - started
            request_count.labels(app.title, request.method, path, str(response.status_code)).inc()
            request_duration.labels(app.title, request.method, path).observe(elapsed)
            response.headers["X-Correlation-ID"] = request_id
            response.headers["X-Process-Time"] = f"{elapsed:.6f}"
            return response
        finally:
            correlation_id.reset(token)

    @app.get("/health", tags=["platform"])
    async def health() -> dict[str, str]:
        return {"status": "ok", "service": app.title}

    @app.get("/metrics", include_in_schema=False)
    async def metrics() -> Response:
        return Response(generate_latest(registry), media_type="text/plain; version=0.0.4")


async def close_common_api_features(app: FastAPI) -> None:
    rate_limiter: RedisTokenBucket | None = getattr(app.state, "rate_limiter", None)
    if rate_limiter is not None:
        await rate_limiter.close()
