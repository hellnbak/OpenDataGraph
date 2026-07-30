from app.services.policy_engine import evaluate_policies, load_policies


def test_policy_bundle_denies_restricted_data_to_public_ai():
    policies = load_policies("policies")
    matches = evaluate_policies(
        {
            "sensitivity": "Restricted",
            "destination_type": "public_ai",
            "agent_status": "approved",
            "action": "send",
            "purpose": "summarization",
        },
        "policies",
    )
    assert len(policies) == 3
    assert matches[0].decision == "deny"
    assert matches[0].policy_id == "deny-restricted-data-to-public-ai"
