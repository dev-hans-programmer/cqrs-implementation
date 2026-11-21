from __future__ import annotations

import logging
from typing import Any

import httpx

from services.shared.api import correlation_id
from services.shared.resilience import CircuitBreaker, CircuitOpenError, backoff

from ..domain.models import CheckoutSaga

logger = logging.getLogger(__name__)


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
        max_attempts: int = 3,
        retry_base_delay_seconds: float = 0.1,
        circuit_failure_threshold: int = 5,
        circuit_recovery_seconds: float = 15.0,
    ) -> None:
        timeout = httpx.Timeout(timeout_seconds)
        self._order = httpx.AsyncClient(base_url=order_service_url, timeout=timeout)
        self._inventory = httpx.AsyncClient(base_url=inventory_service_url, timeout=timeout)
        self._payment = httpx.AsyncClient(base_url=payment_service_url, timeout=timeout)
        self._max_attempts = max_attempts
        self._retry_base_delay_seconds = retry_base_delay_seconds
        self._circuits = {
            name: CircuitBreaker(circuit_failure_threshold, circuit_recovery_seconds)
            for name in ("order-service", "inventory-service", "payment-service")
        }

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
        circuit = self._circuits[service]
        for attempt in range(1, self._max_attempts + 1):
            try:
                await circuit.before_call()
            except CircuitOpenError as exc:
                raise RuntimeError(f"{service} is unavailable: circuit open") from exc
            try:
                response = await client.post(path, json=body, headers=headers)
            except httpx.RequestError as exc:
                await circuit.record_failure()
                if attempt == self._max_attempts:
                    raise RuntimeError(f"{service} is unavailable: {exc}") from exc
                logger.warning(
                    "Transient transport failure service=%s attempt=%s", service, attempt
                )
                await backoff(attempt, self._retry_base_delay_seconds)
                continue

            # Retry only temporary infrastructure failures. A 4xx business decision is final.
            if response.status_code == 429 or response.status_code >= 500:
                await circuit.record_failure()
                if attempt < self._max_attempts:
                    logger.warning(
                        "Transient HTTP failure service=%s status=%s attempt=%s",
                        service,
                        response.status_code,
                        attempt,
                    )
                    await backoff(attempt, self._retry_base_delay_seconds)
                    continue
            else:
                await circuit.record_success()
            if response.is_error:
                raise DownstreamServiceError(service, response)
            return

    @staticmethod
    def _items(saga: CheckoutSaga) -> list[dict[str, object]]:
        return [{"sku": item.sku, "quantity": item.quantity} for item in saga.items]
