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
    return evaluate_policy_definitions(context, load_policies(directory))


def evaluate_policy_definitions(context: dict, policies: list[dict]) -> list[PolicyMatch]:
    validate_policy_definitions(policies)
    matches = []
    for policy in policies:
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


def validate_policy_definitions(policies: list[dict]) -> None:
    if not isinstance(policies, list) or not policies:
        raise ValueError("Policy bundle must contain at least one policy")
    identifiers = set()
    for policy in policies:
        if not isinstance(policy, dict):
            raise ValueError("Each policy must be an object")
        policy_id = policy.get("id")
        if not isinstance(policy_id, str) or not policy_id.strip() or len(policy_id) > 160:
            raise ValueError("Each policy requires a bounded id")
        if policy_id in identifiers:
            raise ValueError(f"Duplicate policy id: {policy_id}")
        identifiers.add(policy_id)
        if policy.get("decision") not in DECISION_ORDER:
            raise ValueError(f"Policy {policy_id} has an invalid decision")
        if not isinstance(policy.get("match", {}), dict):
            raise ValueError(f"Policy {policy_id} match must be an object")
        risk_score = policy.get("risk_score", 50)
        if not isinstance(risk_score, int) or not 0 <= risk_score <= 100:
            raise ValueError(f"Policy {policy_id} risk_score must be from 0 to 100")
        controls = policy.get("controls", [])
        if not isinstance(controls, list) or any(not isinstance(control, str) for control in controls):
            raise ValueError(f"Policy {policy_id} controls must be strings")


def _matches(actual, expected) -> bool:
    expected_values = expected if isinstance(expected, list) else [expected]
    if isinstance(actual, list):
        return bool(set(actual) & set(expected_values))
    return actual in expected_values
