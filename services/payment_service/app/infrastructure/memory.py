import asyncio
from decimal import Decimal

from ..application.handlers import PaymentNotFoundError
from ..domain.events import PaymentChanged
from ..domain.models import Payment, PaymentStatus


class InMemoryPaymentWriteRepository:
    """A fake gateway: the special token `tok_fail` deterministically declines."""

    def __init__(self) -> None:
        self._payments: dict[str, Payment] = {}
        self._idempotency: dict[str, str] = {}
        self._lock = asyncio.Lock()

    async def authorize(
        self,
        payment_id: str,
        order_id: str,
        amount: Decimal,
        payment_method_token: str,
        idempotency_key: str,
    ) -> PaymentChanged:
        async with self._lock:
            previous_id = self._idempotency.get(idempotency_key)
            if previous_id:
                return PaymentChanged(self._payments[previous_id], "payment.authorization_replayed")
            if amount <= 0:
                raise ValueError("Payment amount must be positive")
            if payment_method_token == "tok_fail":
                payment = Payment(
                    payment_id, order_id, amount, PaymentStatus.DECLINED, "Card was declined"
                )
                event_name = "payment.declined"
            else:
                payment = Payment(payment_id, order_id, amount, PaymentStatus.AUTHORIZED)
                event_name = "payment.authorized"
            self._payments[payment.id] = payment
            self._idempotency[idempotency_key] = payment.id
            return PaymentChanged(payment, event_name)

    async def refund(self, payment_id: str) -> PaymentChanged:
        async with self._lock:
            payment = self._payments.get(payment_id)
            if payment is None:
                raise PaymentNotFoundError(payment_id)
            refunded = payment.refund()
            self._payments[payment_id] = refunded
            return PaymentChanged(refunded, "payment.refunded")


class InMemoryPaymentReadModel:
    def __init__(self) -> None:
        self._payments: dict[str, Payment] = {}
        self._lock = asyncio.Lock()

    async def apply(self, event: PaymentChanged) -> None:
        async with self._lock:
            self._payments[event.payment.id] = event.payment

    async def get(self, payment_id: str) -> Payment | None:
        return self._payments.get(payment_id)
