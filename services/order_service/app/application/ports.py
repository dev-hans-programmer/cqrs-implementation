from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Protocol

from ..domain.events import OrderChanged
from ..domain.models import Order, OrderItem, OrderStatus


class OrderWriteRepository(Protocol):
    async def get(self, order_id: str) -> Order | None: ...

    async def get_by_idempotency_key(self, key: str) -> Order | None: ...

    async def save(self, order: Order, idempotency_key: str | None = None) -> None: ...


class OrderReadModel(Protocol):
    async def apply(self, event: OrderChanged) -> None: ...

    async def get(self, order_id: str) -> OrderView | None: ...

    async def list(self) -> list[OrderView]: ...


@dataclass(frozen=True, slots=True)
class OrderView:
    id: str
    customer_id: str
    items: tuple[OrderItem, ...]
    total: Decimal
    status: OrderStatus
    created_at: datetime
    version: int

    @classmethod
    def from_order(cls, order: Order) -> OrderView:
        return cls(
            order.id,
            order.customer_id,
            order.items,
            order.total,
            order.status,
            order.created_at,
            order.version,
        )
