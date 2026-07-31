import argparse
import json
import statistics
import time
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import create_engine, delete, select
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import AIAgent, DataAsset, GraphEdge, RuntimeDecisionReceipt
from app.schemas import AuthZENEvaluationRequest
from app.services.graph import query_graph
from app.services.runtime_authorization import evaluate_access
from app.version import VERSION


BENCHMARK_PROFILES = {
    "local": {"assets": 10_000, "edges": 25_000, "iterations": 50},
    "postgres-small": {"assets": 100_000, "edges": 250_000, "iterations": 100},
    "postgres-large": {"assets": 500_000, "edges": 1_500_000, "iterations": 200},
}


def run_benchmark(
    asset_count: int = 10_000,
    edge_count: int = 25_000,
    iterations: int = 50,
    database_url: str | None = None,
    allow_fixture_writes: bool = False,
    profile_name: str = "local",
) -> dict:
    if not 100 <= asset_count <= 1_000_000:
        raise ValueError("asset_count must be between 100 and 1000000")
    if not 100 <= edge_count <= 2_000_000:
        raise ValueError("edge_count must be between 100 and 2000000")
    if not 5 <= iterations <= 1000:
        raise ValueError("iterations must be between 5 and 1000")
    if profile_name not in BENCHMARK_PROFILES:
        raise ValueError(f"Unsupported benchmark profile: {profile_name}")
    if database_url and not allow_fixture_writes:
        raise ValueError("External benchmarks require allow_fixture_writes=True")
    engine = create_engine(database_url or "sqlite://")
    if database_url and engine.dialect.name != "postgresql":
        raise ValueError("External benchmark profiles require PostgreSQL")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    tenant_id = f"benchmark-{uuid4()}"
    with session_factory() as db:
        try:
            _seed(db, tenant_id, asset_count, edge_count)
            catalog_latencies = _measure(
                iterations,
                lambda index: list(
                    db.scalars(
                        select(DataAsset)
                        .where(
                            DataAsset.tenant_id == tenant_id,
                            DataAsset.source == f"source-{index % 5}",
                            DataAsset.sensitivity == (
                                "Restricted" if index % 7 == 0 else "Internal"
                            ),
                        )
                        .limit(100)
                    ).all()
                ),
            )
            graph_latencies = _measure(
                iterations,
                lambda index: query_graph(
                    db,
                    tenant_id,
                    "asset",
                    str(index % asset_count),
                    3,
                    "outbound",
                    set(),
                ),
            )
            authorization_latencies = _measure(
                iterations,
                lambda index: _authorize(
                    db,
                    tenant_id,
                    index,
                ),
            )
            authorization_batch_size = 10
            authorization_batch_latencies = _measure(
                iterations,
                lambda index: _authorize_batch(
                    db,
                    tenant_id,
                    index,
                    authorization_batch_size,
                ),
            )
        finally:
            if database_url:
                db.execute(
                    delete(RuntimeDecisionReceipt).where(
                        RuntimeDecisionReceipt.tenant_id == tenant_id
                    )
                )
                db.execute(delete(GraphEdge).where(GraphEdge.tenant_id == tenant_id))
                db.execute(delete(DataAsset).where(DataAsset.tenant_id == tenant_id))
                db.execute(delete(AIAgent).where(AIAgent.tenant_id == tenant_id))
                db.commit()
    return {
        "format": "opendatagraph-benchmark",
        "version": 1,
        "application_version": VERSION,
        "captured_at": datetime.now(UTC).isoformat(),
        "profile": {
            "name": profile_name,
            "database": "postgresql" if database_url else "sqlite-memory",
            "assets": asset_count,
            "edges": edge_count,
            "iterations": iterations,
        },
        "operations": {
            "catalog_filter": _latency_summary(catalog_latencies),
            "graph_traversal": _latency_summary(graph_latencies),
            "runtime_authorization": _latency_summary(authorization_latencies),
            "runtime_authorization_batch_10": {
                **_latency_summary(
                    authorization_batch_latencies,
                    operations_per_iteration=authorization_batch_size,
                ),
                "batch_size": authorization_batch_size,
            },
        },
    }


def _seed(db, tenant_id: str, asset_count: int, edge_count: int) -> None:
    db.add(
        AIAgent(
            tenant_id=tenant_id,
            key="benchmark-agent",
            name="Benchmark Agent",
            owner="benchmark@example.test",
            business_purpose="Synthetic performance qualification",
            framework="benchmark",
            models="private-model",
            allowed_domains="",
            max_sensitivity="Restricted",
            allowed_destinations="internal-rag,private-model",
            approval_status="Approved",
            risk_level="Medium",
        )
    )
    db.bulk_save_objects(
        [
            DataAsset(
                tenant_id=tenant_id,
                source=f"source-{index % 5}",
                source_account="benchmark",
                external_id=f"{tenant_id}-asset-{index}",
                name=f"Synthetic asset {index}",
                path=f"/benchmark/{index}",
                owner=f"owner-{index % 100}",
                business_domain=f"domain-{index % 12}",
                sensitivity="Restricted" if index % 7 == 0 else "Internal",
            )
            for index in range(asset_count)
        ]
    )
    db.bulk_save_objects(
        [
            GraphEdge(
                tenant_id=tenant_id,
                source_type="asset",
                source_id=str(index % asset_count),
                relationship="derived_from",
                target_type="asset",
                target_id=str((index + 1) % asset_count),
            )
            for index in range(edge_count)
        ]
    )
    db.commit()


def _authorize(db, tenant_id: str, index: int) -> None:
    request = AuthZENEvaluationRequest.model_validate(
        {
            "subject": {"type": "ai_agent", "id": "benchmark-agent"},
            "resource": {
                "type": "data_asset",
                "id": f"{tenant_id}-asset-{index}",
            },
            "action": {"name": "send"},
            "context": {
                "destination": "internal-rag",
                "purpose": "benchmark",
            },
        }
    )
    evaluate_access(db, tenant_id, request, request_id=f"single-{index}-{uuid4()}")
    db.commit()


def _authorize_batch(db, tenant_id: str, index: int, batch_size: int) -> None:
    for offset in range(batch_size):
        asset_index = (index * batch_size + offset) % 100
        request = AuthZENEvaluationRequest.model_validate(
            {
                "subject": {"type": "ai_agent", "id": "benchmark-agent"},
                "resource": {
                    "type": "data_asset",
                    "id": f"{tenant_id}-asset-{asset_index}",
                },
                "action": {"name": "send"},
                "context": {
                    "destination": "internal-rag",
                    "purpose": "benchmark-batch",
                },
            }
        )
        evaluate_access(
            db,
            tenant_id,
            request,
            request_id=f"batch-{index}-{offset}-{uuid4()}",
        )
    db.commit()


def _measure(iterations: int, operation) -> list[float]:
    latencies = []
    for index in range(iterations):
        started = time.perf_counter()
        operation(index)
        latencies.append((time.perf_counter() - started) * 1000)
    return latencies


def _latency_summary(
    latencies: list[float],
    operations_per_iteration: int = 1,
) -> dict:
    ordered = sorted(latencies)
    total_seconds = sum(ordered) / 1000
    return {
        "p50_ms": round(statistics.median(ordered), 3),
        "p95_ms": round(ordered[max(0, int(len(ordered) * 0.95) - 1)], 3),
        "max_ms": round(max(ordered), 3),
        "operations_per_second": round(
            (len(ordered) * operations_per_iteration) / total_seconds,
            2,
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run deterministic OpenDataGraph benchmarks")
    parser.add_argument("--profile", choices=sorted(BENCHMARK_PROFILES), default="local")
    parser.add_argument("--assets", type=int)
    parser.add_argument("--edges", type=int)
    parser.add_argument("--iterations", type=int)
    parser.add_argument("--database-url")
    parser.add_argument("--allow-fixture-writes", action="store_true")
    args = parser.parse_args()
    profile = BENCHMARK_PROFILES[args.profile]
    print(
        json.dumps(
            run_benchmark(
                args.assets or profile["assets"],
                args.edges or profile["edges"],
                args.iterations or profile["iterations"],
                args.database_url,
                args.allow_fixture_writes,
                args.profile,
            ),
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
