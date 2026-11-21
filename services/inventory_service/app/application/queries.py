from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class GetReservation:
    reservation_id: str


@dataclass(frozen=True, slots=True)
class ListStock:
    pass
