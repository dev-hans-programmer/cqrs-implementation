# 9. Contract Tests

The Saga orchestrator is a consumer of order, inventory, and payment APIs. A provider can be
individually healthy while breaking checkout by renaming a route, removing a field, or changing a
required header.

`tests/contracts/test_http_contracts.py` checks each provider's generated OpenAPI document against
the operations and request fields required by the Saga gateway. It verifies:

- every command and compensation route still exists;
- the expected HTTP method exists;
- request bodies contain required consumer fields;
- creation operations require `Idempotency-Key`.

Run only contract tests:

```bash
pytest -q tests/contracts
```

`tests/test_checkout_end_to_end.py` complements schema contracts by exercising provider behavior
through real ASGI HTTP contracts and checking the final compensated state.

For independently released repositories, publish versioned OpenAPI/Pact artifacts to a contract
broker, verify providers in CI, enforce backward-compatible evolution, and deploy consumers only
against verified provider versions.

