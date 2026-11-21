from typing import Protocol

from ..domain.events import InventoryChanged
from ..domain.models import Reservation, ReservationItem, StockItem


class InventoryWriteRepository(Protocol):
    async def reserve(
        self,
        reservation_id: str,
        order_id: str,
        items: tuple[ReservationItem, ...],
        idempotency_key: str,
    ) -> InventoryChanged: ...

    async def release(self, reservation_id: str) -> InventoryChanged: ...


class InventoryReadModel(Protocol):
    async def apply(self, event: InventoryChanged) -> None: ...

    async def get_reservation(self, reservation_id: str) -> Reservation | None: ...

    async def list_stock(self) -> list[StockItem]: ...
