from __future__ import annotations

import time
from dataclasses import dataclass

from redis.asyncio import Redis

TOKEN_BUCKET_SCRIPT = """
local key = KEYS[1]
local capacity = tonumber(ARGV[1])
local refill = tonumber(ARGV[2])
local now = tonumber(ARGV[3])
local requested = tonumber(ARGV[4])
local values = redis.call('HMGET', key, 'tokens', 'updated')
local tokens = tonumber(values[1]) or capacity
local updated = tonumber(values[2]) or now
tokens = math.min(capacity, tokens + math.max(0, now - updated) * refill)
local allowed = tokens >= requested
if allowed then tokens = tokens - requested end
redis.call('HSET', key, 'tokens', tokens, 'updated', now)
redis.call('EXPIRE', key, math.ceil(capacity / refill) * 2)
return {allowed and 1 or 0, math.floor(tokens)}
"""


@dataclass(frozen=True, slots=True)
class RateLimitDecision:
    allowed: bool
    remaining: int


class RedisTokenBucket:
    """An atomic, distributed token bucket shared by all service replicas."""

    def __init__(self, url: str, capacity: int, refill_per_second: float) -> None:
        self._redis = Redis.from_url(url, decode_responses=True)
        self.capacity = capacity
        self.refill_per_second = refill_per_second

    async def acquire(self, key: str) -> RateLimitDecision:
        result = await self._redis.eval(
            TOKEN_BUCKET_SCRIPT,
            1,
            f"rate-limit:{key}",
            self.capacity,
            self.refill_per_second,
            time.time(),
            1,
        )
        return RateLimitDecision(int(result[0]) == 1, int(result[1]))

    async def close(self) -> None:
        await self._redis.aclose()
