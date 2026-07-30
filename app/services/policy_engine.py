from dataclasses import dataclass
from pathlib import Path

import yaml


DECISION_ORDER = {"allow": 0, "conditional": 1, "deny": 2}


@dataclass(frozen=True)
class PolicyMatch:
    policy_id: str
    version: str
    decision: str
    risk_score: int
    reason: str
    controls: list[str]


def load_policies(directory: str | Path) -> list[dict]:
    policy_directory = Path(directory)
    policies = []
    for path in sorted(policy_directory.glob("*.yaml")):
        with path.open(encoding="utf-8") as handle:
            policy = yaml.safe_load(handle)
        if not isinstance(policy, dict) or not policy.get("id") or policy.get("decision") not in DECISION_ORDER:
            raise ValueError(f"Invalid policy file: {path}")
        policies.append(policy)
    return policies


def evaluate_policies(context: dict, directory: str | Path) -> list[PolicyMatch]:
    matches = []
    for policy in load_policies(directory):
        conditions = policy.get("match", {})
        if all(_matches(context.get(field), expected) for field, expected in conditions.items()):
            matches.append(
                PolicyMatch(
                    policy_id=policy["id"],
                    version=str(policy.get("version", "1")),
                    decision=policy["decision"],
                    risk_score=int(policy.get("risk_score", 50)),
                    reason=policy.get("reason", policy.get("description", policy["id"])),
                    controls=list(policy.get("controls", [])),
                )
            )
    return sorted(matches, key=lambda match: DECISION_ORDER[match.decision], reverse=True)


def _matches(actual, expected) -> bool:
    expected_values = expected if isinstance(expected, list) else [expected]
    if isinstance(actual, list):
        return bool(set(actual) & set(expected_values))
    return actual in expected_values
