from __future__ import annotations

from ..domain.events import OrderChanged
from ..domain.models import Order
from .commands import CancelOrder, ConfirmOrder, CreateOrder
from .ports import OrderReadModel, OrderView, OrderWriteRepository
from .queries import GetOrder, ListOrders


class OrderNotFoundError(LookupError):
    pass


class OrderCommandHandler:
    def __init__(self, write_repo: OrderWriteRepository, read_model: OrderReadModel) -> None:
        self._write_repo = write_repo
        self._read_model = read_model

    async def create(self, command: CreateOrder) -> OrderView:
        existing = await self._write_repo.get_by_idempotency_key(command.idempotency_key)
        if existing is not None:
            # The response can be reconstructed from the source of truth if a retry
            # arrives before/after the projection has been read.
            return OrderView.from_order(existing)
        order = Order.create(command.order_id, command.customer_id, command.items, command.total)
        await self._write_repo.save(order, command.idempotency_key)
        await self._read_model.apply(OrderChanged(order, "order.created"))
        return OrderView.from_order(order)

    async def confirm(self, command: ConfirmOrder) -> OrderView:
        order = await self._require(command.order_id)
        updated = order.confirm()
        await self._write_repo.save(updated)
        await self._read_model.apply(OrderChanged(updated, "order.confirmed"))
        return OrderView.from_order(updated)

    async def cancel(self, command: CancelOrder) -> OrderView:
        order = await self._require(command.order_id)
        updated = order.cancel()
        await self._write_repo.save(updated)
        await self._read_model.apply(OrderChanged(updated, "order.cancelled"))
        return OrderView.from_order(updated)

    async def _require(self, order_id: str) -> Order:
        order = await self._write_repo.get(order_id)
        if order is None:
            raise OrderNotFoundError(order_id)
        return order


class OrderQueryHandler:
    def __init__(self, read_model: OrderReadModel) -> None:
        self._read_model = read_model

    async def get(self, query: GetOrder) -> OrderView:
        result = await self._read_model.get(query.order_id)
        if result is None:
            raise OrderNotFoundError(query.order_id)
        return result

    async def list(self, query: ListOrders) -> list[OrderView]:
        return await self._read_model.list()
