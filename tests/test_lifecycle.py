from datetime import datetime, timedelta
from app.lifecycle import calculate_lifecycle


def test_old_restricted_asset_gets_priority_review():
    now = datetime.utcnow()
    result = calculate_lifecycle(now - timedelta(days=1000), now - timedelta(days=800), now - timedelta(days=800), "Restricted")
    assert result.state == "Stale"
    assert result.action == "Priority owner review"
    assert result.age_days >= 999
