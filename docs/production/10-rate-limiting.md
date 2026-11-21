# 10. Distributed Rate Limiting

Every API can enable a Redis-backed token bucket. Docker enables it by default.

```text
capacity = maximum burst
refill rate = sustained requests per second
```

The middleware identifies callers by `X-Client-ID`, falling back to client IP. One atomic Redis Lua
script refills tokens, consumes a token, updates state, and sets expiry. Because state is in Redis,
all replicas enforce one shared budget.

Rejected requests return:

```text
HTTP 429
X-RateLimit-Limit
X-RateLimit-Remaining
Retry-After
```

`/health` and `/metrics` bypass limiting so orchestration and monitoring remain functional.
Redis failures are fail-open and logged: availability is preferred over turning a limiter outage
into a full application outage. Security-sensitive endpoints may instead require fail-closed
behavior.

Try a small limit by changing Compose values and sending a stable client ID:

```bash
for i in $(seq 1 10); do
  curl -o /dev/null -s -w '%{http_code}\n' \
    -H 'X-Client-ID: learning-client' http://localhost:8000/docs
done
```

Production policies typically distinguish tenant, user, endpoint, cost, and global overload
limits. Protect Redis itself with timeouts and monitor rejection rates and hot keys.

