from pathlib import Path

from fastapi import FastAPI, HTTPException, status

from verifiable_agent_runtime.config import Settings
from verifiable_agent_runtime.ledger import ActionRepository
from verifiable_agent_runtime.models import (
    ActionRecord,
    ActionRequest,
    ApprovalRequest,
    EventRecord,
    LedgerVerification,
    RuntimeMode,
)
from verifiable_agent_runtime.service import (
    ActionNotFoundError,
    IdempotencyConflictError,
    InvalidActionStateError,
    PayloadBindingError,
    RuntimeService,
)


def create_app(
    database_path: Path | None = None,
    mode: RuntimeMode | None = None,
) -> FastAPI:
    settings = Settings.from_environment()
    repository = ActionRepository(database_path or settings.database_path)
    service = RuntimeService(repository, mode or settings.mode)
    application = FastAPI(
        title="Verifiable Agent Runtime",
        version="0.1.0",
        description=(
            "Policy-gated actions with payload-bound approvals and a tamper-evident ledger."
        ),
    )

    @application.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "mode": service.mode.value}

    @application.post(
        "/v1/actions",
        response_model=ActionRecord,
        status_code=status.HTTP_201_CREATED,
    )
    def create_action(request: ActionRequest) -> ActionRecord:
        try:
            return service.create_action(request)
        except IdempotencyConflictError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    @application.get("/v1/actions/{action_id}", response_model=ActionRecord)
    def get_action(action_id: str) -> ActionRecord:
        return _get_action(service, action_id)

    @application.post("/v1/actions/{action_id}/approve", response_model=ActionRecord)
    def approve_action(action_id: str, approval: ApprovalRequest) -> ActionRecord:
        try:
            return service.approve_action(action_id, approval)
        except ActionNotFoundError as error:
            raise HTTPException(status_code=404, detail="Action not found") from error
        except (PayloadBindingError, InvalidActionStateError) as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    @application.get("/v1/actions/{action_id}/events", response_model=list[EventRecord])
    def action_events(action_id: str) -> list[EventRecord]:
        try:
            return service.events(action_id)
        except ActionNotFoundError as error:
            raise HTTPException(status_code=404, detail="Action not found") from error

    @application.get("/v1/actions/{action_id}/verify", response_model=LedgerVerification)
    def verify_action(action_id: str) -> LedgerVerification:
        try:
            return service.verify_ledger(action_id)
        except ActionNotFoundError as error:
            raise HTTPException(status_code=404, detail="Action not found") from error

    return application


def _get_action(service: RuntimeService, action_id: str) -> ActionRecord:
    try:
        return service.get_action(action_id)
    except ActionNotFoundError as error:
        raise HTTPException(status_code=404, detail="Action not found") from error


app = create_app()
