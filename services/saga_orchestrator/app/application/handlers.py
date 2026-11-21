from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from uuid import uuid4

from ..domain.events import SagaChanged
from ..domain.models import CheckoutSaga, SagaStatus, StepStatus
from .commands import StartCheckout
from .ports import CommerceGateway, SagaReadModel, SagaWriteRepository
from .queries import GetSaga

logger = logging.getLogger(__name__)


class SagaNotFoundError(LookupError):
    pass


class CheckoutSagaHandler:
    """An orchestrated Saga: forward actions plus reverse-order compensations."""

    def __init__(
        self,
        write_repo: SagaWriteRepository,
        read_model: SagaReadModel,
        gateway: CommerceGateway,
    ) -> None:
        self._write_repo = write_repo
        self._read_model = read_model
        self._gateway = gateway

    async def execute(self, command: StartCheckout) -> CheckoutSaga:
        existing = await self._write_repo.get_by_idempotency_key(command.idempotency_key)
        if existing is not None:
            return existing

        saga = CheckoutSaga.start(
            uuid4().hex,
            command.idempotency_key,
            command.customer_id,
            command.items,
            command.amount,
            command.payment_method_token,
        )
        await self._persist(saga)
        return await self._continue_forward(saga)

    async def resume(self, saga: CheckoutSaga) -> CheckoutSaga:
        """Resume after a crash; downstream idempotency makes ambiguous calls safe to replay."""

        if saga.status == SagaStatus.RUNNING:
            return await self._continue_forward(saga)
        if saga.status == SagaStatus.COMPENSATING:
            return await self._compensate(saga, self._completed_forward_steps(saga))
        return saga

    async def _continue_forward(self, saga: CheckoutSaga) -> CheckoutSaga:
        completed = self._completed_forward_steps(saga)
        completed_set = set(completed)
        try:
            forward_actions: list[tuple[str, Callable[[CheckoutSaga], Awaitable[None]]]] = [
                ("create_order", self._gateway.create_order),
                ("reserve_inventory", self._gateway.reserve_inventory),
                (
                    "authorize_payment",
                    lambda current: self._gateway.authorize_payment(
                        current, current.payment_method_token
                    ),
                ),
                ("confirm_order", self._gateway.confirm_order),
            ]
            for name, action in forward_actions:
                if name in completed_set:
                    continue
                saga = await self._forward(saga, name, action)
                completed.append(name)
            saga = saga.record("checkout", StepStatus.SUCCEEDED, saga_status=SagaStatus.COMPLETED)
            await self._persist(saga)
            return saga
        except Exception as exc:  # Boundary: downstream failures become Saga state.
            logger.warning("Saga %s failed; starting compensation: %s", saga.id, exc)
            saga = saga.record(
                "forward_execution",
                StepStatus.FAILED,
                str(exc),
                SagaStatus.COMPENSATING,
            )
            await self._persist(saga)
            return await self._compensate(saga, completed)

    @staticmethod
    def _completed_forward_steps(saga: CheckoutSaga) -> list[str]:
        forward_names = {
            "create_order",
            "reserve_inventory",
            "authorize_payment",
            "confirm_order",
        }
        return [
            step.name
            for step in saga.steps
            if step.name in forward_names and step.status == StepStatus.SUCCEEDED
        ]

    async def _forward(
        self,
        saga: CheckoutSaga,
        step_name: str,
        action: Callable[[CheckoutSaga], Awaitable[None]],
    ) -> CheckoutSaga:
        await action(saga)
        updated = saga.record(step_name, StepStatus.SUCCEEDED)
        await self._persist(updated)
        return updated

    async def _compensate(self, saga: CheckoutSaga, completed: list[str]) -> CheckoutSaga:
        actions: dict[str, tuple[str, Callable[[CheckoutSaga], Awaitable[None]]]] = {
            "authorize_payment": ("refund_payment", self._gateway.refund_payment),
            "reserve_inventory": ("release_inventory", self._gateway.release_inventory),
            "create_order": ("cancel_order", self._gateway.cancel_order),
        }
        already_compensated = {
            step.name for step in saga.steps if step.status == StepStatus.COMPENSATED
        }
        compensation_failed = False
        for forward_step in reversed(completed):
            compensation = actions.get(forward_step)
            if compensation is None:
                continue
            name, action = compensation
            if name in already_compensated:
                continue
            try:
                await action(saga)
                saga = saga.record(name, StepStatus.COMPENSATED)
            except Exception as exc:
                compensation_failed = True
                logger.exception("Compensation %s failed for Saga %s", name, saga.id)
                saga = saga.record(name, StepStatus.COMPENSATION_FAILED, str(exc))
            await self._persist(saga)

        final_status = SagaStatus.FAILED if compensation_failed else SagaStatus.COMPENSATED
        saga = saga.record("compensation", StepStatus.SUCCEEDED, saga_status=final_status)
        await self._persist(saga)
        return saga

    async def _persist(self, saga: CheckoutSaga) -> None:
        await self._write_repo.save(saga)
        await self._read_model.apply(SagaChanged(saga))


class SagaQueryHandler:
    def __init__(self, read_model: SagaReadModel) -> None:
        self._read_model = read_model

    async def get(self, query: GetSaga) -> CheckoutSaga:
        saga = await self._read_model.get(query.saga_id)
        if saga is None:
            raise SagaNotFoundError(query.saga_id)
        return saga
