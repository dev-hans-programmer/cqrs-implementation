from dataclasses import dataclass

from ..domain.models import ReservationItem


@dataclass(frozen=True, slots=True)
class ReserveInventory:
    reservation_id: str
    order_id: str
    items: tuple[ReservationItem, ...]
    idempotency_key: str


@dataclass(frozen=True, slots=True)
class ReleaseInventory:
    reservation_id: str
