from typing import Annotated

from fastapi import APIRouter, Header, HTTPException, status

from ..application.commands import ReleaseInventory, ReserveInventory
from ..application.handlers import (
    InventoryCommandHandler,
    InventoryQueryHandler,
    ReservationNotFoundError,
)
from ..application.queries import GetReservation, ListStock
from ..domain.models import InsufficientStockError, ReservationItem
from .schemas import ReservationResponse, ReserveInventoryRequest, StockResponse


def build_router(commands: InventoryCommandHandler, queries: InventoryQueryHandler) -> APIRouter:
    router = APIRouter(prefix="/api/v1", tags=["inventory"])

    @router.post(
        "/reservations", response_model=ReservationResponse, status_code=status.HTTP_201_CREATED
    )
    async def reserve(
        body: ReserveInventoryRequest,
        idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
    ) -> ReservationResponse:
        command = ReserveInventory(
            body.reservation_id,
            body.order_id,
            tuple(ReservationItem(item.sku, item.quantity) for item in body.items),
            idempotency_key,
        )
        try:
            return ReservationResponse.from_domain(await commands.reserve(command))
        except InsufficientStockError as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc

    @router.post("/reservations/{reservation_id}/release", response_model=ReservationResponse)
    async def release(reservation_id: str) -> ReservationResponse:
        try:
            return ReservationResponse.from_domain(
                await commands.release(ReleaseInventory(reservation_id))
            )
        except ReservationNotFoundError as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Reservation not found") from exc

    @router.get("/reservations/{reservation_id}", response_model=ReservationResponse)
    async def get_reservation(reservation_id: str) -> ReservationResponse:
        try:
            result = await queries.get_reservation(GetReservation(reservation_id))
            return ReservationResponse.from_domain(result)
        except ReservationNotFoundError as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Reservation not found") from exc

    @router.get("/stock", response_model=list[StockResponse])
    async def list_stock() -> list[StockResponse]:
        return [StockResponse.from_domain(stock) for stock in await queries.list_stock(ListStock())]

    return router
