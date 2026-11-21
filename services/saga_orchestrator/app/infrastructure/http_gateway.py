from __future__ import annotations

from typing import Any

import httpx

from services.shared.api import correlation_id

from ..domain.models import CheckoutSaga


class DownstreamServiceError(RuntimeError):
    def __init__(self, service: str, response: httpx.Response) -> None:
        try:
            detail = response.json().get("detail", response.text)
        except ValueError:
            detail = response.text
        super().__init__(f"{service} returned {response.status_code}: {detail}")


class HttpCommerceGateway:
    def __init__(
        self,
        order_service_url: str,
        inventory_service_url: str,
        payment_service_url: str,
        timeout_seconds: float = 5.0,
    ) -> None:
        timeout = httpx.Timeout(timeout_seconds)
        self._order = httpx.AsyncClient(base_url=order_service_url, timeout=timeout)
        self._inventory = httpx.AsyncClient(base_url=inventory_service_url, timeout=timeout)
        self._payment = httpx.AsyncClient(base_url=payment_service_url, timeout=timeout)

    async def close(self) -> None:
        await self._order.aclose()
        await self._inventory.aclose()
        await self._payment.aclose()

    async def create_order(self, saga: CheckoutSaga) -> None:
        await self._post(
            self._order,
            "order-service",
            "/api/v1/orders",
            {
                "order_id": saga.order_id,
                "customer_id": saga.customer_id,
                "items": self._items(saga),
                "total": str(saga.amount),
            },
            f"{saga.id}:create-order",
        )

    async def reserve_inventory(self, saga: CheckoutSaga) -> None:
        await self._post(
            self._inventory,
            "inventory-service",
            "/api/v1/reservations",
            {
                "reservation_id": saga.reservation_id,
                "order_id": saga.order_id,
                "items": self._items(saga),
            },
            f"{saga.id}:reserve-inventory",
        )

    async def authorize_payment(self, saga: CheckoutSaga, payment_token: str) -> None:
        await self._post(
            self._payment,
            "payment-service",
            "/api/v1/payments",
            {
                "payment_id": saga.payment_id,
                "order_id": saga.order_id,
                "amount": str(saga.amount),
                "payment_method_token": payment_token,
            },
            f"{saga.id}:authorize-payment",
        )

    async def confirm_order(self, saga: CheckoutSaga) -> None:
        await self._post(
            self._order, "order-service", f"/api/v1/orders/{saga.order_id}/confirm", {}
        )

    async def refund_payment(self, saga: CheckoutSaga) -> None:
        await self._post(
            self._payment,
            "payment-service",
            f"/api/v1/payments/{saga.payment_id}/refund",
            {},
        )

    async def release_inventory(self, saga: CheckoutSaga) -> None:
        await self._post(
            self._inventory,
            "inventory-service",
            f"/api/v1/reservations/{saga.reservation_id}/release",
            {},
        )

    async def cancel_order(self, saga: CheckoutSaga) -> None:
        await self._post(self._order, "order-service", f"/api/v1/orders/{saga.order_id}/cancel", {})

    async def _post(
        self,
        client: httpx.AsyncClient,
        service: str,
        path: str,
        body: dict[str, Any],
        idempotency_key: str | None = None,
    ) -> None:
        headers = {"X-Correlation-ID": correlation_id.get()}
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        try:
            response = await client.post(path, json=body, headers=headers)
        except httpx.RequestError as exc:
            raise RuntimeError(f"{service} is unavailable: {exc}") from exc
        if response.is_error:
            raise DownstreamServiceError(service, response)

    @staticmethod
    def _items(saga: CheckoutSaga) -> list[dict[str, object]]:
        return [{"sku": item.sku, "quantity": item.quantity} for item in saga.items]
