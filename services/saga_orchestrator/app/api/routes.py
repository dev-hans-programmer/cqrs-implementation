from typing import Annotated

from fastapi import APIRouter, Header, HTTPException, status

from ..application.commands import StartCheckout
from ..application.handlers import CheckoutSagaHandler, SagaNotFoundError, SagaQueryHandler
from ..application.queries import GetSaga
from ..domain.models import CheckoutItem
from .schemas import SagaResponse, StartCheckoutRequest


def build_router(commands: CheckoutSagaHandler, queries: SagaQueryHandler) -> APIRouter:
    router = APIRouter(prefix="/api/v1", tags=["checkout"])

    @router.post("/checkouts", response_model=SagaResponse, status_code=status.HTTP_202_ACCEPTED)
    async def start_checkout(
        body: StartCheckoutRequest,
        idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
    ) -> SagaResponse:
        saga = await commands.execute(
            StartCheckout(
                body.customer_id,
                tuple(CheckoutItem(item.sku, item.quantity) for item in body.items),
                body.amount,
                body.payment_method_token,
                idempotency_key,
            )
        )
        return SagaResponse.from_domain(saga)

    @router.get("/sagas/{saga_id}", response_model=SagaResponse)
    async def get_saga(saga_id: str) -> SagaResponse:
        try:
            return SagaResponse.from_domain(await queries.get(GetSaga(saga_id)))
        except SagaNotFoundError as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Saga not found") from exc

    return router
