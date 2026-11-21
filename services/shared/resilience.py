from __future__ import annotations

import asyncio
import random
import time


class CircuitOpenError(RuntimeError):
    pass


class CircuitBreaker:
    """Small async circuit breaker with closed, open, and half-open behavior."""

    def __init__(self, failure_threshold: int = 5, recovery_seconds: float = 15.0) -> None:
        self._threshold = failure_threshold
        self._recovery_seconds = recovery_seconds
        self._failures = 0
        self._opened_at: float | None = None
        self._half_open_call_in_flight = False
        self._lock = asyncio.Lock()

    async def before_call(self) -> None:
        async with self._lock:
            if self._opened_at is None:
                return
            if time.monotonic() - self._opened_at < self._recovery_seconds:
                raise CircuitOpenError("Downstream circuit is open")
            if self._half_open_call_in_flight:
                raise CircuitOpenError("Downstream circuit is half-open")
            self._half_open_call_in_flight = True

    async def record_success(self) -> None:
        async with self._lock:
            self._failures = 0
            self._opened_at = None
            self._half_open_call_in_flight = False

    async def record_failure(self) -> None:
        async with self._lock:
            self._failures += 1
            self._half_open_call_in_flight = False
            if self._failures >= self._threshold:
                self._opened_at = time.monotonic()


async def backoff(attempt: int, base_delay_seconds: float) -> None:
    """Exponential delay with full jitter prevents synchronized retry storms."""

    maximum = base_delay_seconds * (2 ** (attempt - 1))
    await asyncio.sleep(random.uniform(0, maximum))
