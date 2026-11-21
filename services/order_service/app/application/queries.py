from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class GetOrder:
    order_id: str


@dataclass(frozen=True, slots=True)
class ListOrders:
    pass
