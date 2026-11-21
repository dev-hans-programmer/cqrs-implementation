# 6. Durable Saga State and Recovery

`CheckoutSaga` is persisted after every forward and compensation step. Its PostgreSQL row stores
the workflow status, identifiers, completed timeline, failure reason, and tokenized payment-method
reference required to resume.

## Recovery algorithm

`SagaRecoveryWorker` periodically claims stale Sagas in `running` or `compensating` state.
PostgreSQL uses `FOR UPDATE SKIP LOCKED` and a 30-second lease so multiple orchestrator replicas do
not recover the same workflow concurrently.

For a `running` Saga, the handler derives completed forward steps from the durable timeline and
continues with the first missing step. For `compensating`, it skips completed compensations and
continues in reverse order.

```text
Durable steps: create_order succeeded
Recovery runs: reserve -> authorize -> confirm
```

If the process crashed after a downstream service committed but before the Saga recorded the step,
recovery repeats the call. Stable downstream idempotency keys make that ambiguous retry safe.

## Status meaning

- `completed`: checkout succeeded;
- `compensated`: checkout failed and all completed work was reversed;
- `failed`: at least one compensation failed after bounded downstream retries;
- `running` or `compensating`: eligible for stale-work recovery.

Production systems should store a vault reference rather than sensitive payment data, alert on
terminal `failed` Sagas, expose an operator repair workflow, and tune lease duration to the maximum
step execution time.

