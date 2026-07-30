from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass
class Lifecycle:
    age_days: int
    stale_score: int
    state: str
    action: str
    reason: str


def calculate_lifecycle(created_at: datetime | None, modified_at: datetime | None, last_accessed_at: datetime | None, sensitivity: str) -> Lifecycle:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    created = created_at or modified_at or now
    modified = modified_at or created
    activity = last_accessed_at or modified
    age_days = max(0, (now - created).days)
    inactive_days = max(0, (now - activity).days)

    stale_score = min(100, round((inactive_days / 730) * 100))
    if inactive_days >= 730:
        state, action = "Stale", "Owner review"
        reason = f"No observed activity for {inactive_days} days. Validate legal, regulatory, and business retention requirements."
    elif inactive_days >= 365:
        state, action = "Aging", "Archive candidate"
        reason = f"No observed activity for {inactive_days} days. Consider lower-cost storage or archival."
    elif inactive_days >= 180:
        state, action = "Review", "Review retention"
        reason = f"No observed activity for {inactive_days} days. Confirm continued business need."
    else:
        state, action = "Active", "Retain"
        reason = f"Observed activity within {inactive_days} days."

    if sensitivity == "Restricted" and state in {"Stale", "Aging"}:
        action = "Priority owner review"
        reason += " Restricted data increases exposure and should receive expedited review."
    return Lifecycle(age_days, stale_score, state, action, reason)
