from dataclasses import dataclass

from .models import Payment


@dataclass(frozen=True, slots=True)
class PaymentChanged:
    payment: Payment
    event_name: str
