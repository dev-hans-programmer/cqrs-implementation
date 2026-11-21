from decimal import Decimal
from typing import Protocol

from ..domain.events import PaymentChanged
from ..domain.models import Payment


class PaymentWriteRepository(Protocol):
    async def authorize(
        self,
        payment_id: str,
        order_id: str,
        amount: Decimal,
        payment_method_token: str,
        idempotency_key: str,
    ) -> PaymentChanged: ...

    async def refund(self, payment_id: str) -> PaymentChanged: ...


class PaymentReadModel(Protocol):
    async def apply(self, event: PaymentChanged) -> None: ...

    async def get(self, payment_id: str) -> Payment | None: ...
