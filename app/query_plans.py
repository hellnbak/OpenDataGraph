import argparse
import json

from sqlalchemy import create_engine, text


QUERIES = {
    "catalog-filter": """
        SELECT id, external_id, name, sensitivity
        FROM data_assets
        WHERE tenant_id = :tenant_id
          AND source = :source
          AND sensitivity = :sensitivity
        ORDER BY stale_score DESC, id DESC
        LIMIT 100
    """,
    "graph-outbound": """
        SELECT id, source_type, source_id, relationship, target_type, target_id
        FROM graph_edges
        WHERE tenant_id = :tenant_id
          AND source_type = :source_type
          AND source_id = :source_id
        ORDER BY id
        LIMIT 2000
    """,
    "governance-overdue": """
        SELECT id, task_id, task_type, due_at
        FROM governance_review_tasks
        WHERE tenant_id = :tenant_id
          AND status IN ('open', 'in-progress')
          AND due_at < CURRENT_TIMESTAMP
        ORDER BY due_at
        LIMIT 1000
    """,
    "ownership-remediation": """
        SELECT id, assignment_id, campaign_id, remediation_due_at
        FROM ownership_assignments
        WHERE tenant_id = :tenant_id
          AND campaign_id = :campaign_id
          AND status = 'remediation-required'
        ORDER BY remediation_due_at
        LIMIT 1000
    """,
    "runtime-receipts-subject": """
        SELECT receipt_id, decision, policy_decision, risk_score, created_at
        FROM runtime_decision_receipts
        WHERE tenant_id = :tenant_id
          AND subject_type = :runtime_subject_type
          AND subject_id = :runtime_subject_id
        ORDER BY created_at DESC
        LIMIT 1000
    """,
    "runtime-receipts-signing": """
        SELECT id, receipt_id, signing_profile, signing_attempts
        FROM runtime_decision_receipts
        WHERE signing_status = 'pending'
          AND signing_available_at <= CURRENT_TIMESTAMP
        ORDER BY created_at
        LIMIT 100
    """,
    "runtime-receipts-retention": """
        SELECT id, receipt_id, retention_until
        FROM runtime_decision_receipts
        WHERE retention_until < CURRENT_TIMESTAMP
          AND signing_status NOT IN ('pending', 'signing')
        ORDER BY retention_until
        LIMIT 10000
    """,
    "ai-lineage-drift": """
        SELECT event_id, relationship_id, source_type, target_type, observed_at
        FROM ai_lineage_observations
        WHERE tenant_id = :tenant_id
          AND drift_detected = TRUE
        ORDER BY observed_at DESC
        LIMIT 1000
    """,
}


def capture_query_plans(database_url: str, tenant_id: str) -> dict:
    engine = create_engine(database_url, pool_pre_ping=True)
    if engine.dialect.name != "postgresql":
        raise ValueError("Query plan capture requires PostgreSQL")
    parameters = {
        "tenant_id": tenant_id,
        "source": "postgresql",
        "sensitivity": "Restricted",
        "source_type": "asset",
        "source_id": "1",
        "campaign_id": "00000000-0000-0000-0000-000000000000",
        "runtime_subject_type": "ai_agent",
        "runtime_subject_id": "example-agent",
    }
    plans = {}
    try:
        with engine.connect() as connection:
            for name, query in QUERIES.items():
                plan = connection.execute(
                    text(f"EXPLAIN (FORMAT JSON) {query}"),
                    parameters,
                ).scalar_one()
                plans[name] = plan
    finally:
        engine.dispose()
    return {
        "database": "postgresql",
        "analyze": False,
        "tenant_id": tenant_id,
        "plans": plans,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Capture read-only PostgreSQL query plans without ANALYZE"
    )
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--tenant", required=True)
    args = parser.parse_args()
    print(
        json.dumps(
            capture_query_plans(args.database_url, args.tenant),
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
