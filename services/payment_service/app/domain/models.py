from __future__ import annotations

from dataclasses import dataclass, replace
from decimal import Decimal
from enum import StrEnum


class PaymentStatus(StrEnum):
    AUTHORIZED = "authorized"
    DECLINED = "declined"
    REFUNDED = "refunded"


class PaymentDeclinedError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class Payment:
    id: str
    order_id: str
    amount: Decimal
    status: PaymentStatus
    decline_reason: str | None = None

    def refund(self) -> Payment:
        # A replayed compensation must not issue a second refund.
        if self.status == PaymentStatus.REFUNDED:
            return self
        if self.status != PaymentStatus.AUTHORIZED:
            raise ValueError(f"Cannot refund a payment in state {self.status}")
        return replace(self, status=PaymentStatus.REFUNDED)
