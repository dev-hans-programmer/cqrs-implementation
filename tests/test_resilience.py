import asyncio

import pytest

from services.shared.resilience import CircuitBreaker, CircuitOpenError


@pytest.mark.asyncio
async def test_circuit_opens_then_allows_one_half_open_probe() -> None:
    circuit = CircuitBreaker(failure_threshold=2, recovery_seconds=0.01)
    await circuit.record_failure()
    await circuit.record_failure()

    with pytest.raises(CircuitOpenError):
        await circuit.before_call()

    await asyncio.sleep(0.02)
    await circuit.before_call()
    with pytest.raises(CircuitOpenError):
        await circuit.before_call()

    await circuit.record_success()
    await circuit.before_call()
