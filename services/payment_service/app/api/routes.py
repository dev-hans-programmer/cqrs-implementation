from typing import Annotated

from fastapi import APIRouter, Header, HTTPException, status

from ..application.commands import AuthorizePayment, RefundPayment
from ..application.handlers import PaymentCommandHandler, PaymentNotFoundError, PaymentQueryHandler
from ..application.queries import GetPayment
from ..domain.models import PaymentDeclinedError
from .schemas import AuthorizePaymentRequest, PaymentResponse


def build_router(commands: PaymentCommandHandler, queries: PaymentQueryHandler) -> APIRouter:
    router = APIRouter(prefix="/api/v1/payments", tags=["payments"])

    @router.post("", response_model=PaymentResponse, status_code=status.HTTP_201_CREATED)
    async def authorize(
        body: AuthorizePaymentRequest,
        idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
    ) -> PaymentResponse:
        try:
            payment = await commands.authorize(
                AuthorizePayment(
                    body.payment_id,
                    body.order_id,
                    body.amount,
                    body.payment_method_token,
                    idempotency_key,
                )
            )
            return PaymentResponse.from_domain(payment)
        except PaymentDeclinedError as exc:
            raise HTTPException(status.HTTP_402_PAYMENT_REQUIRED, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc

    @router.post("/{payment_id}/refund", response_model=PaymentResponse)
    async def refund(payment_id: str) -> PaymentResponse:
        try:
            return PaymentResponse.from_domain(await commands.refund(RefundPayment(payment_id)))
        except PaymentNotFoundError as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Payment not found") from exc
        except ValueError as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc

    @router.get("/{payment_id}", response_model=PaymentResponse)
    async def get_payment(payment_id: str) -> PaymentResponse:
        try:
            return PaymentResponse.from_domain(await queries.get(GetPayment(payment_id)))
        except PaymentNotFoundError as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Payment not found") from exc

    return router
