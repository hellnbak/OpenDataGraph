import argparse
import json
import statistics
import time

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import DataAsset, GraphEdge
from app.services.graph import query_graph


def run_benchmark(
    asset_count: int = 10_000,
    edge_count: int = 25_000,
    iterations: int = 50,
) -> dict:
    if not 100 <= asset_count <= 1_000_000:
        raise ValueError("asset_count must be between 100 and 1000000")
    if not 100 <= edge_count <= 2_000_000:
        raise ValueError("edge_count must be between 100 and 2000000")
    if not 5 <= iterations <= 1000:
        raise ValueError("iterations must be between 5 and 1000")
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    with session_factory() as db:
        _seed(db, asset_count, edge_count)
        catalog_latencies = _measure(
            iterations,
            lambda index: list(
                db.scalars(
                    select(DataAsset)
                    .where(
                        DataAsset.tenant_id == "benchmark",
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
                "benchmark",
                "asset",
                str(index % asset_count),
                3,
                "outbound",
                set(),
            ),
        )
    return {
        "profile": {
            "database": "sqlite-memory",
            "assets": asset_count,
            "edges": edge_count,
            "iterations": iterations,
        },
        "operations": {
            "catalog_filter": _latency_summary(catalog_latencies),
            "graph_traversal": _latency_summary(graph_latencies),
        },
    }


def _seed(db, asset_count: int, edge_count: int) -> None:
    db.bulk_save_objects(
        [
            DataAsset(
                tenant_id="benchmark",
                source=f"source-{index % 5}",
                source_account="benchmark",
                external_id=f"asset-{index}",
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
                tenant_id="benchmark",
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


def _measure(iterations: int, operation) -> list[float]:
    latencies = []
    for index in range(iterations):
        started = time.perf_counter()
        operation(index)
        latencies.append((time.perf_counter() - started) * 1000)
    return latencies


def _latency_summary(latencies: list[float]) -> dict:
    ordered = sorted(latencies)
    total_seconds = sum(ordered) / 1000
    return {
        "p50_ms": round(statistics.median(ordered), 3),
        "p95_ms": round(ordered[max(0, int(len(ordered) * 0.95) - 1)], 3),
        "max_ms": round(max(ordered), 3),
        "operations_per_second": round(len(ordered) / total_seconds, 2),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run deterministic OpenDataGraph benchmarks")
    parser.add_argument("--assets", type=int, default=10_000)
    parser.add_argument("--edges", type=int, default=25_000)
    parser.add_argument("--iterations", type=int, default=50)
    args = parser.parse_args()
    print(
        json.dumps(
            run_benchmark(args.assets, args.edges, args.iterations),
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
