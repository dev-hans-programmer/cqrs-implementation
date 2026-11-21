from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class GetPayment:
    payment_id: str
