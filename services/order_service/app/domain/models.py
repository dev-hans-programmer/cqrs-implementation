from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum


class OrderStatus(StrEnum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"


@dataclass(frozen=True, slots=True)
class OrderItem:
    sku: str
    quantity: int


@dataclass(frozen=True, slots=True)
class Order:
    id: str
    customer_id: str
    items: tuple[OrderItem, ...]
    total: Decimal
    status: OrderStatus
    created_at: datetime
    version: int = 1

    @classmethod
    def create(
        cls,
        order_id: str,
        customer_id: str,
        items: tuple[OrderItem, ...],
        total: Decimal,
    ) -> Order:
        if not items:
            raise ValueError("An order must contain at least one item")
        if total <= 0:
            raise ValueError("Order total must be positive")
        return cls(order_id, customer_id, items, total, OrderStatus.PENDING, datetime.now(UTC))

    def confirm(self) -> Order:
        if self.status == OrderStatus.CONFIRMED:
            return self
        if self.status != OrderStatus.PENDING:
            raise ValueError(f"Cannot confirm an order in state {self.status}")
        return replace(self, status=OrderStatus.CONFIRMED, version=self.version + 1)

    def cancel(self) -> Order:
        # Cancellation is deliberately idempotent: a retried compensation is safe.
        if self.status == OrderStatus.CANCELLED:
            return self
        if self.status == OrderStatus.CONFIRMED:
            raise ValueError("A confirmed order cannot be cancelled")
        return replace(self, status=OrderStatus.CANCELLED, version=self.version + 1)
