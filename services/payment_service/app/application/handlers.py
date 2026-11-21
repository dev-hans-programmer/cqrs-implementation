from ..domain.models import Payment, PaymentDeclinedError, PaymentStatus
from .commands import AuthorizePayment, RefundPayment
from .ports import PaymentReadModel, PaymentWriteRepository
from .queries import GetPayment


class PaymentNotFoundError(LookupError):
    pass


class PaymentCommandHandler:
    def __init__(self, write_repo: PaymentWriteRepository, read_model: PaymentReadModel) -> None:
        self._write_repo = write_repo
        self._read_model = read_model

    async def authorize(self, command: AuthorizePayment) -> Payment:
        event = await self._write_repo.authorize(
            command.payment_id,
            command.order_id,
            command.amount,
            command.payment_method_token,
            command.idempotency_key,
        )
        await self._read_model.apply(event)
        if event.payment.status == PaymentStatus.DECLINED:
            raise PaymentDeclinedError(event.payment.decline_reason or "Payment declined")
        return event.payment

    async def refund(self, command: RefundPayment) -> Payment:
        event = await self._write_repo.refund(command.payment_id)
        await self._read_model.apply(event)
        return event.payment


class PaymentQueryHandler:
    def __init__(self, read_model: PaymentReadModel) -> None:
        self._read_model = read_model

    async def get(self, query: GetPayment) -> Payment:
        payment = await self._read_model.get(query.payment_id)
        if payment is None:
            raise PaymentNotFoundError(query.payment_id)
        return payment
