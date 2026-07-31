import argparse
import asyncio
import json
import os
import statistics
import time
from urllib.parse import urlparse

import httpx


READ_ENDPOINTS = ("/health", "/ready", "/api/v1/summary")


async def run_soak(
    base_url: str,
    duration_seconds: int = 60,
    concurrency: int = 4,
    requests_per_second: float = 10,
    api_key: str | None = None,
    service_account_key: str | None = None,
) -> dict:
    _validate_options(base_url, duration_seconds, concurrency, requests_per_second)
    if api_key and service_account_key:
        raise ValueError("Provide only one soak authentication credential")
    headers = {}
    if api_key:
        headers["X-API-Key"] = api_key
    if service_account_key:
        headers["X-Service-Account-Key"] = service_account_key
    deadline = time.monotonic() + duration_seconds
    results: list[tuple[str, int, float]] = []
    interval = concurrency / requests_per_second
    timeout = httpx.Timeout(10)
    async with httpx.AsyncClient(
        base_url=base_url.rstrip("/"),
        headers=headers,
        timeout=timeout,
        follow_redirects=False,
    ) as client:
        workers = [
            asyncio.create_task(
                _worker(client, worker, deadline, interval, results)
            )
            for worker in range(concurrency)
        ]
        await asyncio.gather(*workers)
    return _report(base_url, duration_seconds, concurrency, requests_per_second, results)


async def _worker(
    client: httpx.AsyncClient,
    worker: int,
    deadline: float,
    interval: float,
    results: list[tuple[str, int, float]],
) -> None:
    request_index = worker
    while time.monotonic() < deadline:
        endpoint = READ_ENDPOINTS[request_index % len(READ_ENDPOINTS)]
        started = time.perf_counter()
        try:
            response = await client.get(endpoint)
            status = response.status_code
        except httpx.HTTPError:
            status = 0
        results.append((endpoint, status, (time.perf_counter() - started) * 1000))
        request_index += 1
        await asyncio.sleep(interval)


def _report(
    base_url: str,
    duration_seconds: int,
    concurrency: int,
    requests_per_second: float,
    results: list[tuple[str, int, float]],
) -> dict:
    latencies = sorted(result[2] for result in results)
    status_counts: dict[str, int] = {}
    endpoint_counts: dict[str, int] = {}
    for endpoint, status, _latency in results:
        status_counts[str(status)] = status_counts.get(str(status), 0) + 1
        endpoint_counts[endpoint] = endpoint_counts.get(endpoint, 0) + 1
    successful = sum(200 <= status < 400 for _, status, _ in results)
    return {
        "target": urlparse(base_url)._replace(query="", fragment="").geturl(),
        "duration_seconds": duration_seconds,
        "concurrency": concurrency,
        "target_requests_per_second": requests_per_second,
        "requests": len(results),
        "successful": successful,
        "success_rate": round(successful / len(results), 4) if results else 0,
        "status_counts": status_counts,
        "endpoint_counts": endpoint_counts,
        "latency_ms": {
            "p50": round(statistics.median(latencies), 3) if latencies else None,
            "p95": (
                round(latencies[max(0, int(len(latencies) * 0.95) - 1)], 3)
                if latencies
                else None
            ),
            "max": round(max(latencies), 3) if latencies else None,
        },
    }


def _validate_options(
    base_url: str,
    duration_seconds: int,
    concurrency: int,
    requests_per_second: float,
) -> None:
    parsed = urlparse(base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("base_url must be an HTTP or HTTPS URL")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("base_url cannot contain credentials, query parameters, or fragments")
    if not 1 <= duration_seconds <= 86_400:
        raise ValueError("duration_seconds must be between 1 and 86400")
    if not 1 <= concurrency <= 64:
        raise ValueError("concurrency must be between 1 and 64")
    if not 0 < requests_per_second <= 1000:
        raise ValueError("requests_per_second must be greater than 0 and at most 1000")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a bounded read-only OpenDataGraph soak")
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--duration", type=int, default=60)
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--requests-per-second", type=float, default=10)
    args = parser.parse_args()
    result = asyncio.run(
        run_soak(
            args.base_url,
            args.duration,
            args.concurrency,
            args.requests_per_second,
            os.getenv("ODG_SOAK_API_KEY"),
            os.getenv("ODG_SOAK_SERVICE_ACCOUNT_KEY"),
        )
    )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
