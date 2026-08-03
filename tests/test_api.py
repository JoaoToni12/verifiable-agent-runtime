import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from verifiable_agent_runtime.api import create_app
from verifiable_agent_runtime.models import RuntimeMode


@pytest.fixture
def database_path(tmp_path: Path) -> Path:
    return tmp_path / "runtime.sqlite3"


@pytest.fixture
def client(database_path: Path) -> TestClient:
    return TestClient(create_app(database_path=database_path, mode=RuntimeMode.LIVE))


def propose(client: TestClient, tool: str, key: str) -> dict[str, object]:
    response = client.post(
        "/v1/actions",
        json={
            "tool": tool,
            "payload": {"query": "public documentation", "limit": 3},
            "idempotency_key": key,
        },
    )
    assert response.status_code == 201
    return response.json()


def test_read_only_action_executes_and_verifies(client: TestClient) -> None:
    action = propose(client, "knowledge.search", "read-action-001")

    assert action["risk"] == "read"
    assert action["status"] == "executed"
    assert action["result"]["accepted"] is True

    events = client.get(f"/v1/actions/{action['id']}/events").json()
    assert [event["event_type"] for event in events] == [
        "proposed",
        "policy_evaluated",
        "executed",
    ]

    verification = client.get(f"/v1/actions/{action['id']}/verify").json()
    assert verification == {"action_id": action["id"], "valid": True, "event_count": 3}


def test_external_action_requires_payload_bound_approval(client: TestClient) -> None:
    action = propose(client, "message.send", "external-action-001")
    assert action["status"] == "pending_approval"

    wrong_hash = "0" * 64
    rejected = client.post(
        f"/v1/actions/{action['id']}/approve",
        json={"approver": "Demo Reviewer", "payload_hash": wrong_hash},
    )
    assert rejected.status_code == 409

    approved = client.post(
        f"/v1/actions/{action['id']}/approve",
        json={"approver": "Demo Reviewer", "payload_hash": action["payload_hash"]},
    )
    assert approved.status_code == 200
    assert approved.json()["status"] == "executed"

    repeated = client.post(
        f"/v1/actions/{action['id']}/approve",
        json={"approver": "Demo Reviewer", "payload_hash": action["payload_hash"]},
    )
    assert repeated.status_code == 200
    events = client.get(f"/v1/actions/{action['id']}/events").json()
    assert [event["event_type"] for event in events].count("executed") == 1


def test_destructive_and_unknown_tools_are_denied(client: TestClient) -> None:
    destructive = propose(client, "record.delete", "critical-action-001")
    unknown = propose(client, "unregistered.execute", "unknown-action-001")

    assert destructive["risk"] == "critical"
    assert destructive["status"] == "denied"
    assert unknown["risk"] == "critical"
    assert unknown["status"] == "denied"


def test_idempotency_returns_original_action(client: TestClient) -> None:
    original = propose(client, "knowledge.search", "same-request-001")
    repeated = propose(client, "knowledge.search", "same-request-001")

    assert repeated["id"] == original["id"]
    assert repeated["tool"] == original["tool"]


def test_idempotency_rejects_a_different_request(client: TestClient) -> None:
    propose(client, "knowledge.search", "conflicting-request-001")

    conflicting = client.post(
        "/v1/actions",
        json={
            "tool": "message.send",
            "payload": {"query": "public documentation", "limit": 3},
            "idempotency_key": "conflicting-request-001",
        },
    )

    assert conflicting.status_code == 409
    assert conflicting.json() == {
        "detail": "Idempotency key is already bound to a different request"
    }

    conflicting_payload = client.post(
        "/v1/actions",
        json={
            "tool": "knowledge.search",
            "payload": {"query": "different public documentation", "limit": 3},
            "idempotency_key": "conflicting-request-001",
        },
    )

    assert conflicting_payload.status_code == 409


@pytest.mark.parametrize(
    ("mode", "expected_status"),
    [(RuntimeMode.SHADOW, "shadowed"), (RuntimeMode.OFF, "denied")],
)
def test_safe_runtime_modes(
    database_path: Path,
    mode: RuntimeMode,
    expected_status: str,
) -> None:
    client = TestClient(create_app(database_path=database_path, mode=mode))
    action = propose(client, "knowledge.search", f"mode-{mode.value}-001")

    assert action["status"] == expected_status
    assert action["result"] is None


def test_ledger_detects_tampering(client: TestClient, database_path: Path) -> None:
    action = propose(client, "knowledge.search", "tamper-test-001")

    with sqlite3.connect(database_path) as connection:
        connection.execute(
            "UPDATE events SET data_json = ? WHERE action_id = ? AND id = "
            "(SELECT MIN(id) FROM events WHERE action_id = ?)",
            ('{"changed":true}', action["id"], action["id"]),
        )

    verification = client.get(f"/v1/actions/{action['id']}/verify").json()
    assert verification["valid"] is False


def test_request_boundary_rejects_invalid_tool(client: TestClient) -> None:
    response = client.post(
        "/v1/actions",
        json={"tool": "DELETE EVERYTHING", "payload": {}, "idempotency_key": "invalid-001"},
    )

    assert response.status_code == 422
