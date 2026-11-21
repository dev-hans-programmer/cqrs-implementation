import asyncio

from ..domain.events import SagaChanged
from ..domain.models import CheckoutSaga


class InMemorySagaWriteRepository:
    def __init__(self) -> None:
        self._sagas: dict[str, CheckoutSaga] = {}
        self._idempotency: dict[str, str] = {}
        self._lock = asyncio.Lock()

    async def get_by_idempotency_key(self, key: str) -> CheckoutSaga | None:
        saga_id = self._idempotency.get(key)
        return self._sagas.get(saga_id) if saga_id else None

    async def save(self, saga: CheckoutSaga) -> None:
        async with self._lock:
            self._sagas[saga.id] = saga
            self._idempotency[saga.idempotency_key] = saga.id


class InMemorySagaReadModel:
    def __init__(self) -> None:
        self._sagas: dict[str, CheckoutSaga] = {}
        self._lock = asyncio.Lock()

    async def apply(self, event: SagaChanged) -> None:
        async with self._lock:
            self._sagas[event.saga.id] = event.saga

    async def get(self, saga_id: str) -> CheckoutSaga | None:
        return self._sagas.get(saga_id)
