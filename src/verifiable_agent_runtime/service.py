from datetime import UTC, datetime
from uuid import uuid4

from pydantic import JsonValue

from verifiable_agent_runtime.hashing import payload_digest
from verifiable_agent_runtime.ledger import ActionRepository
from verifiable_agent_runtime.models import (
    ActionRecord,
    ActionRequest,
    ActionStatus,
    ApprovalRequest,
    EventRecord,
    EventType,
    LedgerVerification,
    RuntimeMode,
)
from verifiable_agent_runtime.policy import PolicyDecision, PolicyEngine


class ActionNotFoundError(Exception):
    pass


class PayloadBindingError(Exception):
    pass


class IdempotencyConflictError(Exception):
    pass


class InvalidActionStateError(Exception):
    pass


class RuntimeService:
    def __init__(
        self,
        repository: ActionRepository,
        mode: RuntimeMode,
        policy: PolicyEngine | None = None,
    ) -> None:
        self._repository = repository
        self._mode = mode
        self._policy = policy or PolicyEngine()

    @property
    def mode(self) -> RuntimeMode:
        return self._mode

    def create_action(self, request: ActionRequest) -> ActionRecord:
        existing = self._repository.get_by_idempotency_key(request.idempotency_key)
        if existing:
            return self._validate_idempotent_replay(request, existing)

        decision = self._policy.evaluate(request.tool)
        action = self._new_action(request, decision)
        if not self._repository.create(action):
            duplicate = self._repository.get_by_idempotency_key(request.idempotency_key)
            if duplicate:
                return self._validate_idempotent_replay(request, duplicate)
            raise RuntimeError("Idempotency conflict without an existing action")

        self._record_proposal(action, decision)
        return self._apply_policy(action, decision)

    def _validate_idempotent_replay(
        self,
        request: ActionRequest,
        existing: ActionRecord,
    ) -> ActionRecord:
        same_request = existing.tool == request.tool and existing.payload_hash == payload_digest(
            request.payload
        )
        if not same_request:
            raise IdempotencyConflictError(
                "Idempotency key is already bound to a different request"
            )
        return existing

    def get_action(self, action_id: str) -> ActionRecord:
        action = self._repository.get(action_id)
        if action is None:
            raise ActionNotFoundError(action_id)
        return action

    def approve_action(self, action_id: str, approval: ApprovalRequest) -> ActionRecord:
        action = self.get_action(action_id)
        if approval.payload_hash != action.payload_hash:
            raise PayloadBindingError("Approval does not match the proposed payload")
        if action.status is ActionStatus.EXECUTED:
            return action
        if action.status is not ActionStatus.PENDING_APPROVAL:
            raise InvalidActionStateError(f"Cannot approve action in {action.status.value} state")

        self._repository.append_event(
            action.id,
            EventType.APPROVED,
            {"approver": approval.approver, "payload_hash": approval.payload_hash},
        )
        return self._execute(action)

    def events(self, action_id: str) -> list[EventRecord]:
        self.get_action(action_id)
        return self._repository.events(action_id)

    def verify_ledger(self, action_id: str) -> LedgerVerification:
        self.get_action(action_id)
        valid, event_count = self._repository.verify_chain(action_id)
        return LedgerVerification(action_id=action_id, valid=valid, event_count=event_count)

    def _new_action(self, request: ActionRequest, decision: PolicyDecision) -> ActionRecord:
        return ActionRecord(
            id=str(uuid4()),
            created_at=datetime.now(UTC),
            tool=request.tool,
            payload=request.payload,
            payload_hash=payload_digest(request.payload),
            idempotency_key=request.idempotency_key,
            risk=decision.rule.risk,
            status=ActionStatus.PROPOSED,
        )

    def _record_proposal(self, action: ActionRecord, decision: PolicyDecision) -> None:
        self._repository.append_event(
            action.id,
            EventType.PROPOSED,
            {"payload_hash": action.payload_hash, "tool": action.tool},
        )
        self._repository.append_event(
            action.id,
            EventType.POLICY_EVALUATED,
            {
                "allowed": decision.rule.allowed,
                "reason": decision.rule.reason,
                "requires_approval": decision.rule.requires_approval,
                "risk": decision.rule.risk.value,
            },
        )

    def _apply_policy(self, action: ActionRecord, decision: PolicyDecision) -> ActionRecord:
        if self._mode is RuntimeMode.OFF:
            return self._deny(action, "Runtime kill switch is active")
        if self._mode is RuntimeMode.SHADOW:
            return self._shadow(action)
        if not decision.rule.allowed:
            return self._deny(action, decision.rule.reason)
        if decision.rule.requires_approval:
            return self._repository.update(action.id, ActionStatus.PENDING_APPROVAL)
        return self._execute(action)

    def _deny(self, action: ActionRecord, reason: str) -> ActionRecord:
        updated = self._repository.update(action.id, ActionStatus.DENIED)
        self._repository.append_event(action.id, EventType.DENIED, {"reason": reason})
        return updated

    def _shadow(self, action: ActionRecord) -> ActionRecord:
        updated = self._repository.update(action.id, ActionStatus.SHADOWED)
        self._repository.append_event(
            action.id,
            EventType.SHADOWED,
            {"reason": "Shadow mode records the decision without executing"},
        )
        return updated

    def _execute(self, action: ActionRecord) -> ActionRecord:
        result: dict[str, JsonValue] = {
            "accepted": True,
            "payload_hash": action.payload_hash,
            "tool": action.tool,
        }
        updated = self._repository.update(action.id, ActionStatus.EXECUTED, result)
        self._repository.append_event(
            action.id,
            EventType.EXECUTED,
            {"payload_hash": action.payload_hash, "result": result},
        )
        return updated
