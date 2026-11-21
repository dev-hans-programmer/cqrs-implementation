from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4


@dataclass(frozen=True, slots=True)
class EventEnvelope:
    """Broker-safe representation of a domain event."""

    id: str
    name: str
    aggregate_id: str
    payload: dict[str, Any]
    occurred_at: datetime

    @classmethod
    def create(cls, name: str, aggregate_id: str, payload: dict[str, Any]) -> EventEnvelope:
        return cls(uuid4().hex, name, aggregate_id, payload, datetime.now(UTC))

    def to_json(self) -> str:
        return json.dumps(
            {
                "id": self.id,
                "name": self.name,
                "aggregate_id": self.aggregate_id,
                "payload": self.payload,
                "occurred_at": self.occurred_at.isoformat(),
            },
            separators=(",", ":"),
        )

    @classmethod
    def from_json(cls, value: str | bytes) -> EventEnvelope:
        data = json.loads(value)
        return cls(
            id=data["id"],
            name=data["name"],
            aggregate_id=data["aggregate_id"],
            payload=data["payload"],
            occurred_at=datetime.fromisoformat(data["occurred_at"]),
        )
