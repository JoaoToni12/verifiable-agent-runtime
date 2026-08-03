from verifiable_agent_runtime.models import RiskTier
from verifiable_agent_runtime.policy import PolicyEngine


def test_policy_is_fail_closed() -> None:
    decision = PolicyEngine().evaluate("not.registered")

    assert decision.rule.risk is RiskTier.CRITICAL
    assert decision.rule.allowed is False
    assert decision.rule.requires_approval is True
