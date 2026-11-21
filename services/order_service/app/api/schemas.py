from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from ..application.ports import OrderView
from ..domain.models import OrderStatus


class ItemRequest(BaseModel):
    sku: str = Field(min_length=1, max_length=64)
    quantity: int = Field(gt=0, le=1000)


class CreateOrderRequest(BaseModel):
    order_id: str = Field(min_length=1, max_length=64)
    customer_id: str = Field(min_length=1, max_length=64)
    items: list[ItemRequest] = Field(min_length=1)
    total: Decimal = Field(gt=0, max_digits=12, decimal_places=2)


class ItemResponse(BaseModel):
    sku: str
    quantity: int


class OrderResponse(BaseModel):
    id: str
    customer_id: str
    items: list[ItemResponse]
    total: Decimal
    status: OrderStatus
    created_at: datetime
    version: int

    @classmethod
    def from_view(cls, view: OrderView) -> "OrderResponse":
        return cls(
            id=view.id,
            customer_id=view.customer_id,
            items=[ItemResponse(sku=item.sku, quantity=item.quantity) for item in view.items],
            total=view.total,
            status=view.status,
            created_at=view.created_at,
            version=view.version,
        )
