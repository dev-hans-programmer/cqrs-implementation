"""Consumer-driven contract checks for every endpoint used by the Saga gateway."""

from typing import Any

import pytest
from fastapi import FastAPI

from services.inventory_service.app.main import create_app as create_inventory_app
from services.order_service.app.main import create_app as create_order_app
from services.payment_service.app.main import create_app as create_payment_app


@pytest.mark.parametrize(
    ("factory", "required_operations"),
    [
        (
            create_order_app,
            {
                "/api/v1/orders": {"post"},
                "/api/v1/orders/{order_id}/confirm": {"post"},
                "/api/v1/orders/{order_id}/cancel": {"post"},
            },
        ),
        (
            create_inventory_app,
            {
                "/api/v1/reservations": {"post"},
                "/api/v1/reservations/{reservation_id}/release": {"post"},
            },
        ),
        (
            create_payment_app,
            {
                "/api/v1/payments": {"post"},
                "/api/v1/payments/{payment_id}/refund": {"post"},
            },
        ),
    ],
)
def test_provider_openapi_contains_saga_operations(
    factory: Any, required_operations: dict[str, set[str]]
) -> None:
    app: FastAPI = factory()
    paths = app.openapi()["paths"]
    for path, methods in required_operations.items():
        assert path in paths
        assert methods <= set(paths[path])


@pytest.mark.parametrize(
    ("factory", "path", "expected_fields"),
    [
        (
            create_order_app,
            "/api/v1/orders",
            {"order_id", "customer_id", "items", "total"},
        ),
        (
            create_inventory_app,
            "/api/v1/reservations",
            {"reservation_id", "order_id", "items"},
        ),
        (
            create_payment_app,
            "/api/v1/payments",
            {"payment_id", "order_id", "amount", "payment_method_token"},
        ),
    ],
)
def test_provider_command_body_matches_saga_payload(
    factory: Any, path: str, expected_fields: set[str]
) -> None:
    app: FastAPI = factory()
    document = app.openapi()
    operation = document["paths"][path]["post"]
    schema = operation["requestBody"]["content"]["application/json"]["schema"]
    reference = schema["$ref"].split("/")[-1]
    request_schema = document["components"]["schemas"][reference]

    assert expected_fields <= set(request_schema["properties"])
    assert expected_fields <= set(request_schema["required"])
    assert any(parameter["name"] == "Idempotency-Key" for parameter in operation["parameters"])
