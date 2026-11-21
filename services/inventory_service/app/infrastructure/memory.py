import asyncio
from dataclasses import replace

from ..application.handlers import ReservationNotFoundError
from ..domain.events import InventoryChanged
from ..domain.models import (
    InsufficientStockError,
    Reservation,
    ReservationItem,
    ReservationStatus,
    StockItem,
)


class InMemoryInventoryWriteRepository:
    """Locking makes stock checks and reservation writes one atomic transaction."""

    def __init__(self, initial_stock: dict[str, int] | None = None) -> None:
        seed = initial_stock or {"LAPTOP": 10, "HEADPHONES": 25, "KEYBOARD": 15}
        self._stock = {sku: StockItem(sku, quantity) for sku, quantity in seed.items()}
        self._reservations: dict[str, Reservation] = {}
        self._idempotency: dict[str, str] = {}
        self._lock = asyncio.Lock()

    async def reserve(
        self,
        reservation_id: str,
        order_id: str,
        items: tuple[ReservationItem, ...],
        idempotency_key: str,
    ) -> InventoryChanged:
        async with self._lock:
            previous_id = self._idempotency.get(idempotency_key)
            if previous_id:
                previous = self._reservations[previous_id]
                return self._event(previous, "inventory.reservation_replayed")

            # Validate the whole command before changing any stock.
            for requested in items:
                stock = self._stock.get(requested.sku, StockItem(requested.sku, 0))
                if requested.quantity <= 0:
                    raise ValueError("Reservation quantity must be positive")
                if stock.available < requested.quantity:
                    raise InsufficientStockError(requested.sku, requested.quantity, stock.available)

            reservation = Reservation(reservation_id, order_id, items)
            for requested in items:
                stock = self._stock[requested.sku]
                self._stock[requested.sku] = replace(
                    stock, reserved=stock.reserved + requested.quantity
                )
            self._reservations[reservation.id] = reservation
            self._idempotency[idempotency_key] = reservation.id
            return self._event(reservation, "inventory.reserved")

    async def release(self, reservation_id: str) -> InventoryChanged:
        async with self._lock:
            reservation = self._reservations.get(reservation_id)
            if reservation is None:
                raise ReservationNotFoundError(reservation_id)
            if reservation.status == ReservationStatus.RELEASED:
                return self._event(reservation, "inventory.release_replayed")
            for item in reservation.items:
                stock = self._stock[item.sku]
                self._stock[item.sku] = replace(stock, reserved=stock.reserved - item.quantity)
            released = replace(reservation, status=ReservationStatus.RELEASED)
            self._reservations[reservation_id] = released
            return self._event(released, "inventory.released")

    def _event(self, reservation: Reservation, name: str) -> InventoryChanged:
        return InventoryChanged(tuple(self._stock.values()), reservation, name)


class InMemoryInventoryReadModel:
    def __init__(self, initial_stock: dict[str, int] | None = None) -> None:
        seed = initial_stock or {"LAPTOP": 10, "HEADPHONES": 25, "KEYBOARD": 15}
        self._stock = {sku: StockItem(sku, quantity) for sku, quantity in seed.items()}
        self._reservations: dict[str, Reservation] = {}
        self._lock = asyncio.Lock()

    async def apply(self, event: InventoryChanged) -> None:
        async with self._lock:
            self._stock = {stock.sku: stock for stock in event.stocks}
            self._reservations[event.reservation.id] = event.reservation

    async def get_reservation(self, reservation_id: str) -> Reservation | None:
        return self._reservations.get(reservation_id)

    async def list_stock(self) -> list[StockItem]:
        return sorted(self._stock.values(), key=lambda stock: stock.sku)
