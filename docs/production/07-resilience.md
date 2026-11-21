# 7. Timeouts, Retries, and Circuit Breakers

The Saga's `HttpCommerceGateway` applies three distinct controls to downstream HTTP calls.

## Timeout

Every HTTPX client has a finite deadline. A request cannot occupy resources forever. Production
systems often split connect, pool, read, and total deadlines and propagate an overall request
budget.

## Retry

Only temporary failures are retried:

- connection/transport errors;
- HTTP `429`;
- HTTP `5xx`.

Retries use exponential backoff with full jitter. Permanent business outcomes such as `402`
payment decline and `409` insufficient stock are not retried.

Stable idempotency keys are mandatory: a timeout does not prove that the remote operation failed.

## Circuit breaker

Each downstream service has an independent breaker:

```text
closed --failure threshold--> open --cooldown--> half-open probe
half-open --success--> closed
half-open --failure--> open
```

Open circuits fail quickly instead of increasing load on an unhealthy dependency. The breaker is
currently process-local. A local breaker is usually desirable because it reflects each instance's
observations; shared distributed breakers can create correlated outages.

Configuration lives in `.env.example`. `tests/test_resilience.py` verifies open and half-open
behavior.

