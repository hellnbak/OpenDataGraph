import json
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from uuid import uuid4


class EnforcementDenied(PermissionError):
    pass


class OpenDataGraphPEP:
    def __init__(
        self,
        base_url: str,
        pep_id: str,
        *,
        api_key: str = "",
        bearer_token: str = "",
        timeout_seconds: float = 10,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.pep_id = pep_id
        self.api_key = api_key
        self.bearer_token = bearer_token
        self.timeout_seconds = timeout_seconds
        self._handlers: dict[str, Callable[[dict, dict], None]] = {}

    def register_obligation(
        self,
        obligation_id: str,
        handler: Callable[[dict, dict], None],
    ) -> None:
        self._handlers[obligation_id] = handler

    def evaluate(
        self,
        subject: dict,
        resource: dict,
        action: dict,
        context: dict | None = None,
        *,
        idempotency_key: str | None = None,
    ) -> dict:
        headers = {"X-Request-ID": str(uuid4())}
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        return self._request(
            "/access/v1/evaluation",
            {
                "subject": subject,
                "resource": resource,
                "action": action,
                "context": context or {},
            },
            headers,
        )

    def enforce(
        self,
        decision: dict,
        operation: Callable[[], Any],
        *,
        metadata: dict | None = None,
    ) -> Any:
        context = decision.get("context", {})
        receipt_id = context.get("receipt", {}).get("id")
        if not receipt_id:
            raise ValueError("Authorization decision does not contain a receipt id")
        if not decision.get("decision"):
            reason = context.get("reason", "OpenDataGraph policy denied the operation")
            self._report(receipt_id, "rejected", [], reason, metadata)
            raise EnforcementDenied(reason)

        obligations = [
            item
            for item in context.get("obligations", [])
            if item.get("required", True) and item.get("id")
        ]
        satisfied = []
        try:
            for obligation in obligations:
                obligation_id = obligation["id"]
                handler = self._handlers.get(obligation_id)
                if not handler:
                    raise EnforcementDenied(
                        f"No enforcement handler is registered for required obligation {obligation_id}"
                    )
                handler(obligation.get("parameters", {}), decision)
                satisfied.append(obligation_id)
            result = operation()
        except Exception as exc:
            self._report(receipt_id, "failed", satisfied, str(exc), metadata)
            raise
        self._report(receipt_id, "applied", satisfied, None, metadata)
        return result

    def _report(
        self,
        receipt_id: str,
        outcome: str,
        satisfied: list[str],
        reason: str | None,
        metadata: dict | None,
    ) -> dict:
        return self._request(
            "/api/v1/runtime/enforcement-events",
            {
                "event_id": str(uuid4()),
                "receipt_id": receipt_id,
                "pep_id": self.pep_id,
                "outcome": outcome,
                "satisfied_obligations": satisfied,
                "failure_reason": reason,
                "metadata": metadata or {},
                "occurred_at": datetime.now(UTC).isoformat(),
            },
        )

    def _request(
        self,
        path: str,
        payload: dict,
        headers: dict | None = None,
    ) -> dict:
        request_headers = {"Content-Type": "application/json", **(headers or {})}
        if self.bearer_token:
            request_headers["Authorization"] = f"Bearer {self.bearer_token}"
        elif self.api_key:
            request_headers["X-API-Key"] = self.api_key
        request = Request(
            f"{self.base_url}{path}",
            data=json.dumps(payload, separators=(",", ":")).encode(),
            headers=request_headers,
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                return json.loads(response.read())
        except HTTPError as exc:
            detail = exc.read().decode(errors="replace")[:2000]
            raise RuntimeError(f"OpenDataGraph returned HTTP {exc.code}: {detail}") from exc
