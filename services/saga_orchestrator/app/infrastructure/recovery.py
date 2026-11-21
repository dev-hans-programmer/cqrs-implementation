from __future__ import annotations

import asyncio
import logging
from contextlib import suppress

from ..application.handlers import CheckoutSagaHandler
from ..application.ports import SagaWriteRepository

logger = logging.getLogger(__name__)


class SagaRecoveryWorker:
    """Resumes workflows left running or compensating after a process crash."""

    def __init__(
        self,
        repository: SagaWriteRepository,
        handler: CheckoutSagaHandler,
        poll_seconds: float = 5.0,
        stale_after_seconds: float = 10.0,
    ) -> None:
        self._repository = repository
        self._handler = handler
        self._poll_seconds = poll_seconds
        self._stale_after_seconds = stale_after_seconds
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        self._task = asyncio.create_task(self._run(), name="saga-recovery")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            with suppress(asyncio.CancelledError):
                await self._task

    async def _run(self) -> None:
        while True:
            await asyncio.sleep(self._poll_seconds)
            try:
                sagas = await self._repository.list_recoverable(self._stale_after_seconds)
                for saga in sagas:
                    await self._handler.resume(saga)
            except Exception:
                logger.exception("Saga recovery cycle failed")
