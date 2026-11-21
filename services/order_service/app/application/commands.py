from dataclasses import dataclass
from decimal import Decimal

from ..domain.models import OrderItem


@dataclass(frozen=True, slots=True)
class CreateOrder:
    order_id: str
    customer_id: str
    items: tuple[OrderItem, ...]
    total: Decimal
    idempotency_key: str


@dataclass(frozen=True, slots=True)
class ConfirmOrder:
    order_id: str


@dataclass(frozen=True, slots=True)
class CancelOrder:
    order_id: str
