# 8. OpenTelemetry Tracing and Prometheus Metrics

## Tracing

FastAPI and HTTPX are instrumented with OpenTelemetry. Docker applications export OTLP spans to
the collector, which batches them and sends them to Jaeger.

Open `http://localhost:16686`, select `saga-orchestrator`, and trace a checkout across order,
inventory, and payment HTTP calls.

`X-Correlation-ID` remains available in structured logs and responses. Trace IDs support causal
distributed tracing; correlation IDs support human-selected business/request searches. They are
related but not interchangeable.

## Metrics

Each API exposes Prometheus metrics at `/metrics`:

- `http_requests_total` by service, method, route, and status;
- `http_request_duration_seconds` histogram by service, method, and route.

Prometheus scrapes every application and is available at `http://localhost:9090`.

Useful production additions include outbox age, queue depth, projection lag, Saga status counts,
retry counts, circuit state, database-pool saturation, and rate-limit rejection metrics. Alerts
should be derived from user-facing SLOs rather than raw infrastructure thresholds alone.

