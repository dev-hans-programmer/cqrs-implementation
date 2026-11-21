from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum


class SagaStatus(StrEnum):
    RUNNING = "running"
    COMPLETED = "completed"
    COMPENSATING = "compensating"
    COMPENSATED = "compensated"
    FAILED = "failed"


class StepStatus(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    COMPENSATED = "compensated"
    COMPENSATION_FAILED = "compensation_failed"


@dataclass(frozen=True, slots=True)
class CheckoutItem:
    sku: str
    quantity: int


@dataclass(frozen=True, slots=True)
class SagaStep:
    name: str
    status: StepStatus
    occurred_at: datetime
    detail: str | None = None


@dataclass(frozen=True, slots=True)
class CheckoutSaga:
    id: str
    idempotency_key: str
    order_id: str
    reservation_id: str
    payment_id: str
    customer_id: str
    items: tuple[CheckoutItem, ...]
    amount: Decimal
    payment_method_token: str
    status: SagaStatus
    steps: tuple[SagaStep, ...]
    failure_reason: str | None = None

    @classmethod
    def start(
        cls,
        saga_id: str,
        idempotency_key: str,
        customer_id: str,
        items: tuple[CheckoutItem, ...],
        amount: Decimal,
        payment_method_token: str,
    ) -> CheckoutSaga:
        return cls(
            id=saga_id,
            idempotency_key=idempotency_key,
            order_id=f"ord_{saga_id}",
            reservation_id=f"res_{saga_id}",
            payment_id=f"pay_{saga_id}",
            customer_id=customer_id,
            items=items,
            amount=amount,
            payment_method_token=payment_method_token,
            status=SagaStatus.RUNNING,
            steps=(),
        )

    def record(
        self,
        name: str,
        status: StepStatus,
        detail: str | None = None,
        saga_status: SagaStatus | None = None,
    ) -> CheckoutSaga:
        step = SagaStep(name, status, datetime.now(UTC), detail)
        return replace(
            self,
            status=saga_status or self.status,
            steps=(*self.steps, step),
            failure_reason=detail if status == StepStatus.FAILED else self.failure_reason,
        )
