from dataclasses import dataclass

from .models import Reservation, StockItem


@dataclass(frozen=True, slots=True)
class InventoryChanged:
    stocks: tuple[StockItem, ...]
    reservation: Reservation
    event_name: str
