import json
from app.enterprise_demo import PROFILES, generate_enterprise_assets


def test_financial_enterprise_demo_is_weighted_and_synthetic():
    profile, records = generate_enterprise_assets("financial-services", samples=100, seed=7)
    assert profile.key in PROFILES
    assert len(records) == 100
    represented = sum(json.loads(r["metadata_json"])["represented_count"] for r in records)
    assert represented == profile.represented_assets
    assert all(json.loads(r["metadata_json"])["synthetic"] for r in records)
