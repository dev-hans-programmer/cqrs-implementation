from __future__ import annotations

from contextlib import AsyncExitStack
from typing import Any

import httpx
import pytest

from services.inventory_service.app.main import create_app as create_inventory_app
from services.order_service.app.main import create_app as create_order_app
from services.payment_service.app.main import create_app as create_payment_app
from services.saga_orchestrator.app.domain.models import CheckoutSaga
from services.saga_orchestrator.app.main import create_app as create_saga_app


class AsgiCommerceGateway:
    """Routes service calls in process while preserving the real HTTP contracts."""

    def __init__(
        self,
        order: httpx.AsyncClient,
        inventory: httpx.AsyncClient,
        payment: httpx.AsyncClient,
    ) -> None:
        self.order = order
        self.inventory = inventory
        self.payment = payment

    async def _post(
        self,
        client: httpx.AsyncClient,
        path: str,
        body: dict[str, Any],
        key: str | None = None,
    ) -> None:
        headers = {"Idempotency-Key": key} if key else None
        response = await client.post(path, json=body, headers=headers)
        if response.is_error:
            raise RuntimeError(f"downstream returned {response.status_code}: {response.text}")

    @staticmethod
    def items(saga: CheckoutSaga) -> list[dict[str, object]]:
        return [{"sku": item.sku, "quantity": item.quantity} for item in saga.items]

    async def create_order(self, saga: CheckoutSaga) -> None:
        await self._post(
            self.order,
            "/api/v1/orders",
            {
                "order_id": saga.order_id,
                "customer_id": saga.customer_id,
                "items": self.items(saga),
                "total": str(saga.amount),
            },
            f"{saga.id}:order",
        )

    async def reserve_inventory(self, saga: CheckoutSaga) -> None:
        await self._post(
            self.inventory,
            "/api/v1/reservations",
            {
                "reservation_id": saga.reservation_id,
                "order_id": saga.order_id,
                "items": self.items(saga),
            },
            f"{saga.id}:inventory",
        )

    async def authorize_payment(self, saga: CheckoutSaga, payment_token: str) -> None:
        await self._post(
            self.payment,
            "/api/v1/payments",
            {
                "payment_id": saga.payment_id,
                "order_id": saga.order_id,
                "amount": str(saga.amount),
                "payment_method_token": payment_token,
            },
            f"{saga.id}:payment",
        )

    async def confirm_order(self, saga: CheckoutSaga) -> None:
        await self._post(self.order, f"/api/v1/orders/{saga.order_id}/confirm", {})

    async def refund_payment(self, saga: CheckoutSaga) -> None:
        await self._post(self.payment, f"/api/v1/payments/{saga.payment_id}/refund", {})

    async def release_inventory(self, saga: CheckoutSaga) -> None:
        await self._post(self.inventory, f"/api/v1/reservations/{saga.reservation_id}/release", {})

    async def cancel_order(self, saga: CheckoutSaga) -> None:
        await self._post(self.order, f"/api/v1/orders/{saga.order_id}/cancel", {})


async def clients() -> tuple[AsyncExitStack, dict[str, httpx.AsyncClient]]:
    stack = AsyncExitStack()
    result: dict[str, httpx.AsyncClient] = {}
    apps = {
        "order": create_order_app(),
        "inventory": create_inventory_app(),
        "payment": create_payment_app(),
    }
    for name, app in apps.items():
        result[name] = await stack.enter_async_context(
            httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=f"http://{name}")
        )
    gateway = AsgiCommerceGateway(result["order"], result["inventory"], result["payment"])
    result["saga"] = await stack.enter_async_context(
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=create_saga_app(gateway)),
            base_url="http://saga",
        )
    )
    return stack, result


@pytest.mark.asyncio
async def test_declined_payment_releases_stock_and_cancels_order() -> None:
    stack, service = await clients()
    async with stack:
        checkout = await service["saga"].post(
            "/api/v1/checkouts",
            headers={"Idempotency-Key": "failed-checkout"},
            json={
                "customer_id": "customer-1",
                "items": [{"sku": "LAPTOP", "quantity": 1}],
                "amount": "999.00",
                "payment_method_token": "tok_fail",
            },
        )
        body = checkout.json()
        assert checkout.status_code == 202
        assert body["status"] == "compensated"

        order = await service["order"].get(f"/api/v1/orders/{body['order_id']}")
        stock = await service["inventory"].get("/api/v1/stock")
        assert order.json()["status"] == "cancelled"
        laptop = next(item for item in stock.json() if item["sku"] == "LAPTOP")
        assert laptop["available"] == laptop["on_hand"]
