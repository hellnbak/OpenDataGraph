# Ownership Campaigns

Ownership campaigns create bounded, auditable catalog attestation work for one tenant.

## Scope and launch

Data owners create a draft campaign with a name, description, future deadline, optional escalation policy, and optional scope:

- `source`
- `business_domain`
- `sensitivity`
- `owner`

Each scope value may be one string or a list of strings. Unknown fields, empty values, and oversized lists are rejected.

Launching a campaign selects matching assets in stable identifier order and creates at most the requested `max_assets` assignments. The assignment snapshots the current owner. Assets discovered after launch are not added automatically.

## Recurring schedules

Data owners can create interval or five-field cron schedules with an IANA time zone, maintenance windows, due days, asset limit, scope, optional escalation policy, and optional enabled integration endpoint identifiers. Workers atomically claim each occurrence and enqueue a reference-only `ownership.campaign.launch` job.

The scheduled occurrence timestamp produces a stable campaign identity, so a retried job does not create a duplicate campaign. A scope that matches no assets fails safely and follows normal job retry behavior.

## Attestation

An assignment can be confirmed with the current owner or a corrected owner. Confirmation updates the catalog owner and records the attesting identity, note, owner, and timestamp.

An unconfirmed assignment requires:

- a remediation action;
- a future remediation due date.

The assignment moves to `remediation-required`. Data owners can update its action and deadline, then resolve it explicitly. A campaign completes when no assignment remains pending or remediation-required.

## Escalation policies

An escalation policy contains one to twenty unique stages. Each stage defines a stable key, an offset from campaign due time in hours, a recipient class (`owner`, `data-owner`, or `administrator`), and optional enabled integration endpoint identifiers. Negative offsets are reminders; zero and positive offsets are due or overdue escalations.

The worker records one durable event for each campaign and stage, claims it safely across replicas, and queues endpoint deliveries with a stable idempotency key. Failed stage claims retry with bounded delay, and stale running claims recover after `ODG_WORKER_CLAIM_TIMEOUT_SECONDS`. Recipient values are routing metadata; OpenDataGraph does not send email directly.

Auditors can inspect bounded daily trend analytics for launches, completions, assignments, attestations, remediation resolution, response times, active overdue campaigns, and overdue nonresponses.

## APIs

- `POST|GET /api/v1/ownership/campaigns`
- `GET /api/v1/ownership/campaigns/{campaign_id}`
- `POST /api/v1/ownership/campaigns/{campaign_id}/launch`
- `GET /api/v1/ownership/campaigns/{campaign_id}/assignments`
- `POST /api/v1/ownership/assignments/{assignment_id}/attest`
- `PATCH /api/v1/ownership/assignments/{assignment_id}/remediation`
- `POST /api/v1/ownership/assignments/{assignment_id}/resolve`
- `POST|GET /api/v1/ownership/schedules`
- `PATCH|DELETE /api/v1/ownership/schedules/{schedule_id}`
- `POST|GET /api/v1/ownership/escalation-policies`
- `PATCH /api/v1/ownership/escalation-policies/{policy_id}`
- `GET /api/v1/ownership/escalation-events`
- `GET /api/v1/ownership/analytics/trends`

Auditors can read campaigns and assignments. Data owners create, launch, attest, remediate, and resolve.

## Operating guidance

- Use narrow campaigns with accountable owners and realistic deadlines.
- Review `unknown` owners before broad sensitivity campaigns.
- Do not treat campaign completion as proof of external-system entitlement review.
- Re-run campaigns after material catalog growth or organizational changes.
- Subscribe integrations to `ownership.campaign.launched`, `ownership.campaign.reminder`, `ownership.campaign.escalated`, `ownership.assignment.remediation-required`, and `ownership.campaign.completed`, or select explicit enabled destinations on a schedule or escalation stage.
- Preserve assignment records as governance evidence according to organizational retention requirements.
