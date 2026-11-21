from dataclasses import dataclass
from decimal import Decimal

from ..domain.models import CheckoutItem


@dataclass(frozen=True, slots=True)
class StartCheckout:
    customer_id: str
    items: tuple[CheckoutItem, ...]
    amount: Decimal
    payment_method_token: str
    idempotency_key: str
