from dataclasses import dataclass

from .models import CheckoutSaga


@dataclass(frozen=True, slots=True)
class SagaChanged:
    saga: CheckoutSaga
