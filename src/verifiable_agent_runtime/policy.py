from dataclasses import dataclass
from types import MappingProxyType

from verifiable_agent_runtime.models import RiskTier


@dataclass(frozen=True, slots=True)
class PolicyRule:
    risk: RiskTier
    allowed: bool
    requires_approval: bool
    reason: str


@dataclass(frozen=True, slots=True)
class PolicyDecision:
    tool: str
    rule: PolicyRule


_RULES = MappingProxyType(
    {
        "knowledge.search": PolicyRule(RiskTier.READ, True, False, "Read-only operation"),
        "draft.generate": PolicyRule(RiskTier.PROPOSE, True, False, "Draft has no side effect"),
        "ticket.create": PolicyRule(
            RiskTier.REVERSIBLE, True, True, "Reversible write requires approval"
        ),
        "message.send": PolicyRule(
            RiskTier.EXTERNAL, True, True, "External communication requires approval"
        ),
        "record.delete": PolicyRule(
            RiskTier.CRITICAL, False, True, "Destructive operation is blocked"
        ),
    }
)

_UNKNOWN_RULE = PolicyRule(
    RiskTier.CRITICAL,
    False,
    True,
    "Unknown tools are denied by default",
)


class PolicyEngine:
    def evaluate(self, tool: str) -> PolicyDecision:
        return PolicyDecision(tool=tool, rule=_RULES.get(tool, _UNKNOWN_RULE))
