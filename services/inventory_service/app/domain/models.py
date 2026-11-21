from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ReservationStatus(StrEnum):
    ACTIVE = "active"
    RELEASED = "released"


class InsufficientStockError(ValueError):
    def __init__(self, sku: str, requested: int, available: int) -> None:
        super().__init__(
            f"Insufficient stock for {sku}: requested={requested}, available={available}"
        )
        self.sku = sku
        self.requested = requested
        self.available = available


@dataclass(frozen=True, slots=True)
class ReservationItem:
    sku: str
    quantity: int


@dataclass(frozen=True, slots=True)
class StockItem:
    sku: str
    on_hand: int
    reserved: int = 0

    @property
    def available(self) -> int:
        return self.on_hand - self.reserved


@dataclass(frozen=True, slots=True)
class Reservation:
    id: str
    order_id: str
    items: tuple[ReservationItem, ...]
    status: ReservationStatus = ReservationStatus.ACTIVE
