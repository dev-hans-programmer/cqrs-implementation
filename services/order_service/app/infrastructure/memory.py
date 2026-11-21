import asyncio

from ..application.ports import OrderView
from ..domain.events import OrderChanged
from ..domain.models import Order


class InMemoryOrderWriteRepository:
    """Write store. Replace with a transactional repository in a real deployment."""

    def __init__(self) -> None:
        self._orders: dict[str, Order] = {}
        self._idempotency: dict[str, str] = {}
        self._lock = asyncio.Lock()

    async def get(self, order_id: str) -> Order | None:
        return self._orders.get(order_id)

    async def get_by_idempotency_key(self, key: str) -> Order | None:
        order_id = self._idempotency.get(key)
        return self._orders.get(order_id) if order_id else None

    async def save(self, order: Order, idempotency_key: str | None = None) -> None:
        async with self._lock:
            current = self._orders.get(order.id)
            if current is not None and order.version < current.version:
                raise RuntimeError("Optimistic concurrency conflict")
            self._orders[order.id] = order
            if idempotency_key:
                self._idempotency[idempotency_key] = order.id


class InMemoryOrderReadModel:
    """Denormalized query store, updated from domain events."""

    def __init__(self) -> None:
        self._views: dict[str, OrderView] = {}
        self._lock = asyncio.Lock()

    async def apply(self, event: OrderChanged) -> None:
        async with self._lock:
            self._views[event.order.id] = OrderView.from_order(event.order)

    async def get(self, order_id: str) -> OrderView | None:
        return self._views.get(order_id)

    async def list(self) -> list[OrderView]:
        return sorted(self._views.values(), key=lambda order: order.created_at)
