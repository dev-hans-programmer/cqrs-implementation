from ..domain.models import Reservation, StockItem
from .commands import ReleaseInventory, ReserveInventory
from .ports import InventoryReadModel, InventoryWriteRepository
from .queries import GetReservation, ListStock


class ReservationNotFoundError(LookupError):
    pass


class InventoryCommandHandler:
    def __init__(
        self, write_repo: InventoryWriteRepository, read_model: InventoryReadModel
    ) -> None:
        self._write_repo = write_repo
        self._read_model = read_model

    async def reserve(self, command: ReserveInventory) -> Reservation:
        event = await self._write_repo.reserve(
            command.reservation_id,
            command.order_id,
            command.items,
            command.idempotency_key,
        )
        await self._read_model.apply(event)
        return event.reservation

    async def release(self, command: ReleaseInventory) -> Reservation:
        event = await self._write_repo.release(command.reservation_id)
        await self._read_model.apply(event)
        return event.reservation


class InventoryQueryHandler:
    def __init__(self, read_model: InventoryReadModel) -> None:
        self._read_model = read_model

    async def get_reservation(self, query: GetReservation) -> Reservation:
        result = await self._read_model.get_reservation(query.reservation_id)
        if result is None:
            raise ReservationNotFoundError(query.reservation_id)
        return result

    async def list_stock(self, query: ListStock) -> list[StockItem]:
        return await self._read_model.list_stock()
