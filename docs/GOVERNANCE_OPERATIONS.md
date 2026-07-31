# Governance Operations

OpenDataGraph v1.6 unifies policy and evidence approvals in a tenant-scoped operational review queue and adds broader posture analytics and metadata-only evidence packages.

## Task sources

The platform creates tasks for:

- `policy-approval` when a policy bundle is submitted;
- `policy-exception-renewal` when an exception requests a later expiry;
- `evidence-disposition` when evidence deletion is requested.

Creating the same open task type and subject is idempotent. Approval or rejection completes every matching open task and records the outcome, completion identity, and timestamp.

## Queue

Auditors list tasks through:

```text
GET /api/v1/governance/reviews
```

Filters include status, task type, assignee, overdue state, and a bounded result limit. Statuses are `open`, `in-progress`, and `completed`.

Data owners assign open work through:

```text
PATCH /api/v1/governance/reviews/{task_id}/assign
```

Assignment moves the task to `in-progress`. It does not grant the assignee permission to approve the underlying governed object; normal role, delegation, and separation-of-duty checks remain authoritative.

## SLA metrics

`GET /api/v1/governance/sla` reports:

- total, open, completed, overdue, and due-soon counts;
- average completed resolution time;
- total, open, overdue, and completed counts by task type.

`ODG_GOVERNANCE_DEFAULT_SLA_HOURS` controls default due dates. `ODG_GOVERNANCE_DUE_SOON_HOURS` controls the reporting window.

`GET /api/v1/governance/analytics` adds bounded-window SLA compliance, aging, ownership remediation, evidence disposition, service-account credential, and policy-decision posture. See [Governance analytics and evidence packages](GOVERNANCE_EVIDENCE_PACKAGES.md).

## Notifications

Administrators enqueue bounded overdue evaluation through:

```text
POST /api/v1/governance/notifications/jobs?limit=500
```

The `governance.sla-notify` worker job emits `governance.review.overdue` to enabled subscribed integrations. A task records notification time only when at least one delivery is queued. Delivery, retry, dead-letter, replay, allowlist, and event-format controls remain those documented in [Integrations](INTEGRATIONS.md).

## Operations

- Review overdue and unassigned work daily.
- Alert on queue growth, repeated job failures, and dead letters.
- Keep review SLAs aligned with evidence retention and policy change windows.
- Preserve separation of request, assignment, approval, and execution responsibilities where required.
- Treat integration notification as an alert, not as the approval decision itself.
