import argparse
import json
from pathlib import Path

from app.services.evidence_signing import verify_evidence_package


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Verify an OpenDataGraph governance evidence package",
    )
    parser.add_argument("package", type=Path)
    parser.add_argument("--profile")
    parser.add_argument("--require-trusted", action="store_true")
    args = parser.parse_args()
    result = verify_evidence_package(args.package.read_bytes(), args.profile)
    print(json.dumps(result, indent=2, sort_keys=True))
    if not result["valid"] or (args.require_trusted and not result["trusted"]):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
