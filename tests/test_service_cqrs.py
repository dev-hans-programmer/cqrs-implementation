from decimal import Decimal

import httpx
import pytest

from services.inventory_service.app.main import create_app as create_inventory_app
from services.order_service.app.main import create_app as create_order_app
from services.payment_service.app.main import create_app as create_payment_app


@pytest.mark.asyncio
async def test_order_command_updates_a_separate_query_projection() -> None:
    transport = httpx.ASGITransport(app=create_order_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://order") as client:
        created = await client.post(
            "/api/v1/orders",
            headers={"Idempotency-Key": "create-1"},
            json={
                "order_id": "order-1",
                "customer_id": "customer-1",
                "items": [{"sku": "LAPTOP", "quantity": 1}],
                "total": "999.00",
            },
        )
        assert created.status_code == 201

        # This GET is handled by the query side, not by the write repository.
        queried = await client.get("/api/v1/orders/order-1")
        assert queried.json()["status"] == "pending"

        confirmed = await client.post("/api/v1/orders/order-1/confirm")
        assert confirmed.json()["status"] == "confirmed"
        assert confirmed.json()["version"] == 2


@pytest.mark.asyncio
async def test_inventory_reservation_is_atomic_and_idempotent() -> None:
    transport = httpx.ASGITransport(app=create_inventory_app({"LAPTOP": 1}))
    async with httpx.AsyncClient(transport=transport, base_url="http://inventory") as client:
        payload = {
            "reservation_id": "reservation-1",
            "order_id": "order-1",
            "items": [{"sku": "LAPTOP", "quantity": 1}],
        }
        first = await client.post(
            "/api/v1/reservations", headers={"Idempotency-Key": "reserve-1"}, json=payload
        )
        replay = await client.post(
            "/api/v1/reservations", headers={"Idempotency-Key": "reserve-1"}, json=payload
        )
        unavailable = await client.post(
            "/api/v1/reservations",
            headers={"Idempotency-Key": "reserve-2"},
            json={**payload, "reservation_id": "reservation-2"},
        )

        assert first.status_code == replay.status_code == 201
        assert unavailable.status_code == 409
        stock = (await client.get("/api/v1/stock")).json()[0]
        assert stock["reserved"] == 1  # The replay did not reserve twice.


@pytest.mark.asyncio
async def test_payment_decline_is_queryable() -> None:
    transport = httpx.ASGITransport(app=create_payment_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://payment") as client:
        response = await client.post(
            "/api/v1/payments",
            headers={"Idempotency-Key": "payment-1"},
            json={
                "payment_id": "payment-1",
                "order_id": "order-1",
                "amount": str(Decimal("10.00")),
                "payment_method_token": "tok_fail",
            },
        )
        assert response.status_code == 402
        payment = await client.get("/api/v1/payments/payment-1")
        assert payment.json()["status"] == "declined"
