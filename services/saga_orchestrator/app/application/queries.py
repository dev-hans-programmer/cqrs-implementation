from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class GetSaga:
    saga_id: str
