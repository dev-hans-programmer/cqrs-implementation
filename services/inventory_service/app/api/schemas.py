from pydantic import BaseModel, Field

from ..domain.models import Reservation, ReservationStatus, StockItem


class ReservationItemRequest(BaseModel):
    sku: str = Field(min_length=1, max_length=64)
    quantity: int = Field(gt=0, le=1000)


class ReserveInventoryRequest(BaseModel):
    reservation_id: str = Field(min_length=1, max_length=64)
    order_id: str = Field(min_length=1, max_length=64)
    items: list[ReservationItemRequest] = Field(min_length=1)


class ReservationItemResponse(BaseModel):
    sku: str
    quantity: int


class ReservationResponse(BaseModel):
    id: str
    order_id: str
    items: list[ReservationItemResponse]
    status: ReservationStatus

    @classmethod
    def from_domain(cls, reservation: Reservation) -> "ReservationResponse":
        return cls(
            id=reservation.id,
            order_id=reservation.order_id,
            items=[
                ReservationItemResponse(sku=item.sku, quantity=item.quantity)
                for item in reservation.items
            ],
            status=reservation.status,
        )


class StockResponse(BaseModel):
    sku: str
    on_hand: int
    reserved: int
    available: int

    @classmethod
    def from_domain(cls, stock: StockItem) -> "StockResponse":
        return cls(
            sku=stock.sku,
            on_hand=stock.on_hand,
            reserved=stock.reserved,
            available=stock.available,
        )
