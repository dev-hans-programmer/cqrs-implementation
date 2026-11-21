from dataclasses import dataclass

from .models import Order


@dataclass(frozen=True, slots=True)
class OrderChanged:
    """Local domain event consumed synchronously by the in-memory projection."""

    order: Order
    event_name: str
