from decimal import Decimal

import pytest

from services.saga_orchestrator.app.application.commands import StartCheckout
from services.saga_orchestrator.app.application.handlers import CheckoutSagaHandler
from services.saga_orchestrator.app.domain.models import (
    CheckoutItem,
    CheckoutSaga,
    SagaStatus,
    StepStatus,
)
from services.saga_orchestrator.app.infrastructure.memory import (
    InMemorySagaReadModel,
    InMemorySagaWriteRepository,
)


class RecordingGateway:
    def __init__(self, fail_at: str | None = None) -> None:
        self.calls: list[str] = []
        self.fail_at = fail_at

    async def _call(self, name: str) -> None:
        self.calls.append(name)
        if self.fail_at == name:
            raise RuntimeError(f"forced {name} failure")

    async def create_order(self, saga: CheckoutSaga) -> None:
        await self._call("create_order")

    async def reserve_inventory(self, saga: CheckoutSaga) -> None:
        await self._call("reserve_inventory")

    async def authorize_payment(self, saga: CheckoutSaga, payment_token: str) -> None:
        await self._call("authorize_payment")

    async def confirm_order(self, saga: CheckoutSaga) -> None:
        await self._call("confirm_order")

    async def refund_payment(self, saga: CheckoutSaga) -> None:
        await self._call("refund_payment")

    async def release_inventory(self, saga: CheckoutSaga) -> None:
        await self._call("release_inventory")

    async def cancel_order(self, saga: CheckoutSaga) -> None:
        await self._call("cancel_order")


def command(key: str = "checkout-1") -> StartCheckout:
    return StartCheckout(
        "customer-1", (CheckoutItem("LAPTOP", 1),), Decimal("100.00"), "tok_ok", key
    )


@pytest.mark.asyncio
async def test_successful_saga_runs_each_forward_step() -> None:
    gateway = RecordingGateway()
    handler = CheckoutSagaHandler(InMemorySagaWriteRepository(), InMemorySagaReadModel(), gateway)

    saga = await handler.execute(command())

    assert saga.status == SagaStatus.COMPLETED
    assert gateway.calls == [
        "create_order",
        "reserve_inventory",
        "authorize_payment",
        "confirm_order",
    ]


@pytest.mark.asyncio
async def test_payment_failure_compensates_in_reverse_order() -> None:
    gateway = RecordingGateway(fail_at="authorize_payment")
    handler = CheckoutSagaHandler(InMemorySagaWriteRepository(), InMemorySagaReadModel(), gateway)

    saga = await handler.execute(command())

    assert saga.status == SagaStatus.COMPENSATED
    assert gateway.calls == [
        "create_order",
        "reserve_inventory",
        "authorize_payment",
        "release_inventory",
        "cancel_order",
    ]
    assert [step.name for step in saga.steps[-3:]] == [
        "release_inventory",
        "cancel_order",
        "compensation",
    ]


@pytest.mark.asyncio
async def test_idempotency_key_does_not_run_saga_twice() -> None:
    gateway = RecordingGateway()
    write_repo = InMemorySagaWriteRepository()
    handler = CheckoutSagaHandler(write_repo, InMemorySagaReadModel(), gateway)

    first = await handler.execute(command())
    replay = await handler.execute(command())

    assert replay.id == first.id
    assert len(gateway.calls) == 4


@pytest.mark.asyncio
async def test_recovery_resumes_after_the_last_durable_step() -> None:
    gateway = RecordingGateway()
    write_repo = InMemorySagaWriteRepository()
    handler = CheckoutSagaHandler(write_repo, InMemorySagaReadModel(), gateway)
    interrupted = CheckoutSaga.start(
        "saga-recovery-1",
        "recovery-key",
        "customer-1",
        (CheckoutItem("LAPTOP", 1),),
        Decimal("100.00"),
        "tok_ok",
    ).record("create_order", StepStatus.SUCCEEDED)
    await write_repo.save(interrupted)

    recovered = await handler.resume(interrupted)

    assert recovered.status == SagaStatus.COMPLETED
    assert gateway.calls == ["reserve_inventory", "authorize_payment", "confirm_order"]
