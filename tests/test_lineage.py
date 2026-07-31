from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.services.graph import ingest_openlineage_event, query_graph


def test_openlineage_ingestion_is_idempotent_and_queryable():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    event = {
        "eventType": "COMPLETE",
        "eventTime": "2026-07-30T20:00:00Z",
        "producer": "https://example.test/lineage",
        "run": {"runId": "run-1"},
        "job": {"namespace": "analytics", "name": "customer-rollup"},
        "inputs": [{"namespace": "warehouse", "name": "customers"}],
        "outputs": [{"namespace": "warehouse", "name": "customer_summary"}],
    }
    with session_factory() as db:
        first = ingest_openlineage_event(db, "tenant-a", event)
        second = ingest_openlineage_event(db, "tenant-a", event)
        assert first["edges_created"] == 4
        assert second["idempotent"] is True
        result = query_graph(
            db,
            "tenant-a",
            "dataset",
            "warehouse/customers",
            max_depth=3,
            direction="outbound",
            relationships=set(),
        )
        nodes = {(node["type"], node["id"]) for node in result["nodes"]}
        assert ("lineage-job", "analytics/customer-rollup") in nodes
        assert ("dataset", "warehouse/customer_summary") in nodes
        isolated = query_graph(
            db,
            "tenant-b",
            "dataset",
            "warehouse/customers",
            max_depth=3,
            direction="both",
            relationships=set(),
        )
        assert len(isolated["nodes"]) == 1
        assert isolated["edges"] == []
