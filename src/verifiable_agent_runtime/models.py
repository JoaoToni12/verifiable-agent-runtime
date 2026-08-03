from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator


class RiskTier(StrEnum):
    READ = "read"
    PROPOSE = "propose"
    REVERSIBLE = "reversible"
    EXTERNAL = "external"
    CRITICAL = "critical"


class ActionStatus(StrEnum):
    PROPOSED = "proposed"
    PENDING_APPROVAL = "pending_approval"
    EXECUTED = "executed"
    DENIED = "denied"
    SHADOWED = "shadowed"


class RuntimeMode(StrEnum):
    LIVE = "live"
    SHADOW = "shadow"
    OFF = "off"


class EventType(StrEnum):
    PROPOSED = "proposed"
    POLICY_EVALUATED = "policy_evaluated"
    APPROVED = "approved"
    EXECUTED = "executed"
    DENIED = "denied"
    SHADOWED = "shadowed"


class ActionRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    tool: str = Field(min_length=3, max_length=80, pattern=r"^[a-z][a-z0-9_.-]+$")
    payload: dict[str, JsonValue]
    idempotency_key: str = Field(min_length=8, max_length=120, pattern=r"^[A-Za-z0-9_.:-]+$")


class ApprovalRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    approver: str = Field(min_length=3, max_length=120)
    payload_hash: str = Field(pattern=r"^[a-f0-9]{64}$")

    @field_validator("approver")
    @classmethod
    def normalize_approver(cls, value: str) -> str:
        return " ".join(value.split())


class ActionRecord(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    created_at: datetime
    tool: str
    payload: dict[str, JsonValue]
    payload_hash: str
    idempotency_key: str
    risk: RiskTier
    status: ActionStatus
    result: dict[str, JsonValue] | None = None


class EventRecord(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: int
    action_id: str
    created_at: datetime
    event_type: EventType
    data: dict[str, JsonValue]
    previous_hash: str
    event_hash: str


class LedgerVerification(BaseModel):
    model_config = ConfigDict(frozen=True)

    action_id: str
    valid: bool
    event_count: int
