# OpenDataGraph Python Enforcement SDK

`OpenDataGraphPEP` evaluates AuthZEN requests, applies every required obligation through explicitly registered handlers, denies when a handler is missing, and reports the enforcement outcome against the decision receipt.

```python
from opendatagraph_enforcement import OpenDataGraphPEP

pep = OpenDataGraphPEP("https://governance.example", "payments-api", bearer_token="...")
pep.register_obligation("audit-log", lambda parameters, decision: record_audit(parameters))
decision = pep.evaluate(
    {"type": "ai_agent", "id": "payments-copilot"},
    {"type": "data_asset", "id": "dataset://payments"},
    {"name": "send"},
    {"destination": "private-model", "purpose": "fraud-review"},
)
result = pep.enforce(decision, lambda: invoke_model())
```

Treat bearer tokens as short-lived secrets. Keep obligation handlers deterministic, fail closed, and avoid placing prompts, responses, credentials, or customer content in enforcement metadata.
