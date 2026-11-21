from decimal import Decimal

from pydantic import BaseModel, Field

from ..domain.models import Payment, PaymentStatus


class AuthorizePaymentRequest(BaseModel):
    payment_id: str = Field(min_length=1, max_length=64)
    order_id: str = Field(min_length=1, max_length=64)
    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    payment_method_token: str = Field(min_length=1, max_length=128)


class PaymentResponse(BaseModel):
    id: str
    order_id: str
    amount: Decimal
    status: PaymentStatus
    decline_reason: str | None

    @classmethod
    def from_domain(cls, payment: Payment) -> "PaymentResponse":
        return cls(
            id=payment.id,
            order_id=payment.order_id,
            amount=payment.amount,
            status=payment.status,
            decline_reason=payment.decline_reason,
        )
