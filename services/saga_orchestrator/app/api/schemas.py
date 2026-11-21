from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from ..domain.models import CheckoutSaga, SagaStatus, StepStatus


class CheckoutItemRequest(BaseModel):
    sku: str = Field(min_length=1, max_length=64)
    quantity: int = Field(gt=0, le=1000)


class StartCheckoutRequest(BaseModel):
    customer_id: str = Field(min_length=1, max_length=64)
    items: list[CheckoutItemRequest] = Field(min_length=1)
    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    payment_method_token: str = Field(min_length=1, max_length=128)


class SagaStepResponse(BaseModel):
    name: str
    status: StepStatus
    occurred_at: datetime
    detail: str | None


class SagaResponse(BaseModel):
    id: str
    order_id: str
    reservation_id: str
    payment_id: str
    status: SagaStatus
    steps: list[SagaStepResponse]
    failure_reason: str | None

    @classmethod
    def from_domain(cls, saga: CheckoutSaga) -> "SagaResponse":
        return cls(
            id=saga.id,
            order_id=saga.order_id,
            reservation_id=saga.reservation_id,
            payment_id=saga.payment_id,
            status=saga.status,
            steps=[
                SagaStepResponse(
                    name=step.name,
                    status=step.status,
                    occurred_at=step.occurred_at,
                    detail=step.detail,
                )
                for step in saga.steps
            ],
            failure_reason=saga.failure_reason,
        )
