# Ownership Campaigns

Ownership campaigns create bounded, auditable catalog attestation work for one tenant.

## Scope and launch

Data owners create a draft campaign with a name, description, future deadline, and optional scope:

- `source`
- `business_domain`
- `sensitivity`
- `owner`

Each scope value may be one string or a list of strings. Unknown fields, empty values, and oversized lists are rejected.

Launching a campaign selects matching assets in stable identifier order and creates at most the requested `max_assets` assignments. The assignment snapshots the current owner. Assets discovered after launch are not added automatically.

## Attestation

An assignment can be confirmed with the current owner or a corrected owner. Confirmation updates the catalog owner and records the attesting identity, note, owner, and timestamp.

An unconfirmed assignment requires:

- a remediation action;
- a future remediation due date.

The assignment moves to `remediation-required`. Data owners can update its action and deadline, then resolve it explicitly. A campaign completes when no assignment remains pending or remediation-required.

## APIs

- `POST|GET /api/v1/ownership/campaigns`
- `GET /api/v1/ownership/campaigns/{campaign_id}`
- `POST /api/v1/ownership/campaigns/{campaign_id}/launch`
- `GET /api/v1/ownership/campaigns/{campaign_id}/assignments`
- `POST /api/v1/ownership/assignments/{assignment_id}/attest`
- `PATCH /api/v1/ownership/assignments/{assignment_id}/remediation`
- `POST /api/v1/ownership/assignments/{assignment_id}/resolve`

Auditors can read campaigns and assignments. Data owners create, launch, attest, remediate, and resolve.

## Operating guidance

- Use narrow campaigns with accountable owners and realistic deadlines.
- Review `unknown` owners before broad sensitivity campaigns.
- Do not treat campaign completion as proof of external-system entitlement review.
- Re-run campaigns after material catalog growth or organizational changes.
- Preserve assignment records as governance evidence according to organizational retention requirements.
