import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from app.version import VERSION


LATENCY_METRICS = {"p50_ms", "p95_ms", "max_ms"}
THROUGHPUT_METRICS = {"operations_per_second"}
PLAN_KEYS = {
    "Node Type",
    "Parent Relationship",
    "Parallel Aware",
    "Async Capable",
    "Join Type",
    "Index Name",
    "Relation Name",
    "Schema",
    "Strategy",
}
FORBIDDEN_TOPOLOGY_KEYS = {
    "authorization",
    "credential",
    "database_url",
    "dsn",
    "password",
    "secret",
    "token",
}


def capture_baseline(
    benchmark_report: dict,
    topology: dict,
    query_plan_report: dict | None = None,
) -> dict:
    _validate_benchmark_report(benchmark_report)
    _validate_topology(topology)
    fingerprints = query_plan_fingerprints(query_plan_report) if query_plan_report else {}
    return {
        "format": "opendatagraph-performance-baseline",
        "version": 1,
        "application_version": benchmark_report.get("application_version", VERSION),
        "captured_at": datetime.now(UTC).isoformat(),
        "topology": topology,
        "profile": benchmark_report["profile"],
        "operations": benchmark_report["operations"],
        "query_plan_fingerprints": fingerprints,
        "qualification": "comparative-not-certified-capacity",
    }


def compare_baseline(
    baseline: dict,
    benchmark_report: dict,
    query_plan_report: dict | None = None,
    max_latency_regression_percent: float = 20.0,
    max_throughput_regression_percent: float = 20.0,
    fail_on_plan_drift: bool = False,
) -> dict:
    _validate_baseline(baseline)
    _validate_benchmark_report(benchmark_report)
    if not 0 <= max_latency_regression_percent <= 1000:
        raise ValueError("Maximum latency regression percent is invalid")
    if not 0 <= max_throughput_regression_percent <= 1000:
        raise ValueError("Maximum throughput regression percent is invalid")
    comparisons = {}
    passed = True
    for operation, baseline_metrics in baseline["operations"].items():
        current_metrics = benchmark_report["operations"].get(operation)
        if not current_metrics:
            comparisons[operation] = {"passed": False, "error": "operation-missing"}
            passed = False
            continue
        metrics = {}
        operation_passed = True
        for metric in sorted(LATENCY_METRICS | THROUGHPUT_METRICS):
            baseline_value = float(baseline_metrics[metric])
            current_value = float(current_metrics[metric])
            if metric in LATENCY_METRICS:
                regression = _regression_percent(
                    baseline_value,
                    current_value - baseline_value,
                )
                metric_passed = regression <= max_latency_regression_percent
            else:
                regression = _regression_percent(
                    baseline_value,
                    baseline_value - current_value,
                )
                metric_passed = regression <= max_throughput_regression_percent
            metrics[metric] = {
                "baseline": baseline_value,
                "current": current_value,
                "regression_percent": round(regression, 3),
                "passed": metric_passed,
            }
            operation_passed = operation_passed and metric_passed
        comparisons[operation] = {"passed": operation_passed, "metrics": metrics}
        passed = passed and operation_passed
    baseline_plans = baseline.get("query_plan_fingerprints", {})
    current_plans = query_plan_fingerprints(query_plan_report) if query_plan_report else {}
    plan_drift = {
        name: {
            "baseline": fingerprint,
            "current": current_plans.get(name),
            "changed": current_plans.get(name) != fingerprint,
        }
        for name, fingerprint in baseline_plans.items()
    }
    if fail_on_plan_drift and any(item["changed"] for item in plan_drift.values()):
        passed = False
    return {
        "passed": passed,
        "baseline_application_version": baseline.get("application_version"),
        "current_application_version": benchmark_report.get("application_version", VERSION),
        "thresholds": {
            "max_latency_regression_percent": max_latency_regression_percent,
            "max_throughput_regression_percent": max_throughput_regression_percent,
            "fail_on_plan_drift": fail_on_plan_drift,
        },
        "operations": comparisons,
        "query_plan_drift": plan_drift,
    }


def query_plan_fingerprints(query_plan_report: dict | None) -> dict[str, str]:
    if not query_plan_report:
        return {}
    if query_plan_report.get("analyze") is not False or not isinstance(
        query_plan_report.get("plans"),
        dict,
    ):
        raise ValueError("Query plan report must contain read-only plan objects")
    return {
        name: hashlib.sha256(
            json.dumps(
                _normalized_plan(plan),
                separators=(",", ":"),
                sort_keys=True,
            ).encode()
        ).hexdigest()
        for name, plan in sorted(query_plan_report["plans"].items())
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Capture or compare OpenDataGraph performance baselines",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    capture = subparsers.add_parser("capture")
    capture.add_argument("--benchmark", type=Path, required=True)
    capture.add_argument("--topology", type=Path, required=True)
    capture.add_argument("--query-plans", type=Path)
    capture.add_argument("--output", type=Path, required=True)
    compare = subparsers.add_parser("compare")
    compare.add_argument("--baseline", type=Path, required=True)
    compare.add_argument("--benchmark", type=Path, required=True)
    compare.add_argument("--query-plans", type=Path)
    compare.add_argument("--max-latency-regression-percent", type=float, default=20.0)
    compare.add_argument("--max-throughput-regression-percent", type=float, default=20.0)
    compare.add_argument("--fail-on-plan-drift", action="store_true")
    args = parser.parse_args()
    if args.command == "capture":
        result = capture_baseline(
            _load_json(args.benchmark),
            _load_json(args.topology),
            _load_json(args.query_plans) if args.query_plans else None,
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(result, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return
    result = compare_baseline(
        _load_json(args.baseline),
        _load_json(args.benchmark),
        _load_json(args.query_plans) if args.query_plans else None,
        args.max_latency_regression_percent,
        args.max_throughput_regression_percent,
        args.fail_on_plan_drift,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    if not result["passed"]:
        raise SystemExit(1)


def _validate_benchmark_report(report: dict) -> None:
    if not isinstance(report, dict) or not isinstance(report.get("profile"), dict):
        raise ValueError("Benchmark report profile is invalid")
    operations = report.get("operations")
    if not isinstance(operations, dict) or not operations:
        raise ValueError("Benchmark report operations are invalid")
    required = LATENCY_METRICS | THROUGHPUT_METRICS
    for metrics in operations.values():
        if not isinstance(metrics, dict) or not required <= set(metrics):
            raise ValueError("Benchmark report metrics are incomplete")
        if any(
            not isinstance(metrics[name], (int, float)) or metrics[name] < 0
            for name in required
        ):
            raise ValueError("Benchmark report metrics are invalid")


def _validate_baseline(baseline: dict) -> None:
    if baseline.get("format") != "opendatagraph-performance-baseline":
        raise ValueError("Performance baseline format is invalid")
    _validate_benchmark_report(
        {"profile": baseline.get("profile"), "operations": baseline.get("operations")}
    )


def _validate_topology(topology: dict) -> None:
    if not isinstance(topology, dict) or not isinstance(topology.get("name"), str):
        raise ValueError("Reference topology requires a name")

    def inspect(value: object, path: tuple[str, ...] = ()) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                if not isinstance(key, str) or key.lower() in FORBIDDEN_TOPOLOGY_KEYS:
                    raise ValueError("Reference topology cannot contain secrets or connection strings")
                inspect(item, (*path, key))
        elif isinstance(value, list):
            if len(value) > 100:
                raise ValueError("Reference topology list is too large")
            for item in value:
                inspect(item, path)
        elif not isinstance(value, (str, int, float, bool, type(None))):
            raise ValueError("Reference topology contains an unsupported value")
        elif isinstance(value, str) and len(value) > 2000:
            raise ValueError("Reference topology value is too large")

    inspect(topology)


def _normalized_plan(value: object) -> object:
    if isinstance(value, list):
        return [_normalized_plan(item) for item in value]
    if not isinstance(value, dict):
        return value
    normalized = {
        key: _normalized_plan(item)
        for key, item in value.items()
        if key in PLAN_KEYS or key in {"Plan", "Plans"}
    }
    return normalized


def _regression_percent(baseline: float, delta: float) -> float:
    if baseline == 0:
        return 0.0 if delta <= 0 else 1000.0
    return max(0.0, (delta / baseline) * 100)


def _load_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Unable to load JSON from {path}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"JSON document must be an object: {path}")
    return value


if __name__ == "__main__":
    main()
