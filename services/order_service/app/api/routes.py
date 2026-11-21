from typing import Annotated

from fastapi import APIRouter, Header, HTTPException, status

from ..application.commands import CancelOrder, ConfirmOrder, CreateOrder
from ..application.handlers import OrderCommandHandler, OrderNotFoundError, OrderQueryHandler
from ..application.queries import GetOrder, ListOrders
from ..domain.models import OrderItem
from .schemas import CreateOrderRequest, OrderResponse


def build_router(commands: OrderCommandHandler, queries: OrderQueryHandler) -> APIRouter:
    router = APIRouter(prefix="/api/v1/orders", tags=["orders"])

    @router.post("", response_model=OrderResponse, status_code=status.HTTP_201_CREATED)
    async def create_order(
        body: CreateOrderRequest,
        idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
    ) -> OrderResponse:
        command = CreateOrder(
            body.order_id,
            body.customer_id,
            tuple(OrderItem(item.sku, item.quantity) for item in body.items),
            body.total,
            idempotency_key,
        )
        try:
            return OrderResponse.from_view(await commands.create(command))
        except ValueError as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc

    @router.post("/{order_id}/confirm", response_model=OrderResponse)
    async def confirm_order(order_id: str) -> OrderResponse:
        try:
            return OrderResponse.from_view(await commands.confirm(ConfirmOrder(order_id)))
        except OrderNotFoundError as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Order not found") from exc
        except ValueError as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc

    @router.post("/{order_id}/cancel", response_model=OrderResponse)
    async def cancel_order(order_id: str) -> OrderResponse:
        try:
            return OrderResponse.from_view(await commands.cancel(CancelOrder(order_id)))
        except OrderNotFoundError as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Order not found") from exc
        except ValueError as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc

    @router.get("/{order_id}", response_model=OrderResponse)
    async def get_order(order_id: str) -> OrderResponse:
        try:
            return OrderResponse.from_view(await queries.get(GetOrder(order_id)))
        except OrderNotFoundError as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Order not found") from exc

    @router.get("", response_model=list[OrderResponse])
    async def list_orders() -> list[OrderResponse]:
        return [OrderResponse.from_view(view) for view in await queries.list(ListOrders())]

    return router
