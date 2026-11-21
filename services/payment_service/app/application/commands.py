from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class AuthorizePayment:
    payment_id: str
    order_id: str
    amount: Decimal
    payment_method_token: str
    idempotency_key: str


@dataclass(frozen=True, slots=True)
class RefundPayment:
    payment_id: str
