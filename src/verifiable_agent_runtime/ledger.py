import json
import sqlite3
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import JsonValue

from verifiable_agent_runtime.hashing import canonical_json, event_digest
from verifiable_agent_runtime.models import (
    ActionRecord,
    ActionStatus,
    EventRecord,
    EventType,
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS actions (
    id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    tool TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    idempotency_key TEXT NOT NULL UNIQUE,
    risk TEXT NOT NULL,
    status TEXT NOT NULL,
    result_json TEXT
);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    action_id TEXT NOT NULL REFERENCES actions(id),
    created_at TEXT NOT NULL,
    event_type TEXT NOT NULL,
    data_json TEXT NOT NULL,
    previous_hash TEXT NOT NULL,
    event_hash TEXT NOT NULL UNIQUE
);
CREATE INDEX IF NOT EXISTS idx_events_action_id ON events(action_id, id);
"""


class ActionRepository:
    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path
        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self._database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._connection() as connection:
            connection.executescript(_SCHEMA)

    def create(self, action: ActionRecord) -> bool:
        values = (
            action.id,
            action.created_at.isoformat(),
            action.tool,
            canonical_json(action.payload),
            action.payload_hash,
            action.idempotency_key,
            action.risk.value,
            action.status.value,
            None,
        )
        query = "INSERT INTO actions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)"
        try:
            with self._connection() as connection:
                connection.execute(query, values)
        except sqlite3.IntegrityError:
            return False
        return True

    def get(self, action_id: str) -> ActionRecord | None:
        return self._get_by("id", action_id)

    def get_by_idempotency_key(self, key: str) -> ActionRecord | None:
        return self._get_by("idempotency_key", key)

    def _get_by(self, column: str, value: str) -> ActionRecord | None:
        with self._connection() as connection:
            row = connection.execute(
                f"SELECT * FROM actions WHERE {column} = ?", (value,)
            ).fetchone()
        return _to_action(row) if row else None

    def update(
        self,
        action_id: str,
        status: ActionStatus,
        result: Mapping[str, JsonValue] | None = None,
    ) -> ActionRecord:
        result_json = canonical_json(result) if result is not None else None
        query = "UPDATE actions SET status = ?, result_json = ? WHERE id = ?"
        with self._connection() as connection:
            connection.execute(query, (status.value, result_json, action_id))
        action = self.get(action_id)
        if action is None:
            raise RuntimeError(f"Action disappeared during update: {action_id}")
        return action

    def append_event(
        self,
        action_id: str,
        event_type: EventType,
        data: Mapping[str, JsonValue],
    ) -> EventRecord:
        created_at = datetime.now(UTC).isoformat()
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            previous_hash = _last_hash(connection, action_id)
            digest_input = _event_input(action_id, event_type, data, created_at, previous_hash)
            event_hash = event_digest(digest_input)
            cursor = connection.execute(
                "INSERT INTO events "
                "(action_id, created_at, event_type, data_json, previous_hash, event_hash) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    action_id,
                    created_at,
                    event_type.value,
                    canonical_json(data),
                    previous_hash,
                    event_hash,
                ),
            )
            if cursor.lastrowid is None:
                raise RuntimeError("Event insert did not return an identifier")
            event_id = cursor.lastrowid
        return EventRecord(
            id=event_id,
            action_id=action_id,
            created_at=datetime.fromisoformat(created_at),
            event_type=event_type,
            data=dict(data),
            previous_hash=previous_hash,
            event_hash=event_hash,
        )

    def events(self, action_id: str) -> list[EventRecord]:
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT * FROM events WHERE action_id = ? ORDER BY id", (action_id,)
            ).fetchall()
        return [_to_event(row) for row in rows]

    def verify_chain(self, action_id: str) -> tuple[bool, int]:
        events = self.events(action_id)
        previous_hash = "0" * 64
        for event in events:
            expected = event_digest(
                _event_input(
                    event.action_id,
                    event.event_type,
                    event.data,
                    event.created_at.isoformat(),
                    previous_hash,
                )
            )
            if event.previous_hash != previous_hash or event.event_hash != expected:
                return False, len(events)
            previous_hash = event.event_hash
        return True, len(events)


def _last_hash(connection: sqlite3.Connection, action_id: str) -> str:
    row = connection.execute(
        "SELECT event_hash FROM events WHERE action_id = ? ORDER BY id DESC LIMIT 1",
        (action_id,),
    ).fetchone()
    return str(row["event_hash"]) if row else "0" * 64


def _event_input(
    action_id: str,
    event_type: EventType,
    data: Mapping[str, JsonValue],
    created_at: str,
    previous_hash: str,
) -> dict[str, Any]:
    return {
        "action_id": action_id,
        "created_at": created_at,
        "data": data,
        "event_type": event_type.value,
        "previous_hash": previous_hash,
    }


def _to_action(row: sqlite3.Row) -> ActionRecord:
    result = json.loads(row["result_json"]) if row["result_json"] else None
    return ActionRecord(
        id=row["id"],
        created_at=datetime.fromisoformat(row["created_at"]),
        tool=row["tool"],
        payload=json.loads(row["payload_json"]),
        payload_hash=row["payload_hash"],
        idempotency_key=row["idempotency_key"],
        risk=row["risk"],
        status=row["status"],
        result=result,
    )


def _to_event(row: sqlite3.Row) -> EventRecord:
    return EventRecord(
        id=row["id"],
        action_id=row["action_id"],
        created_at=datetime.fromisoformat(row["created_at"]),
        event_type=row["event_type"],
        data=json.loads(row["data_json"]),
        previous_hash=row["previous_hash"],
        event_hash=row["event_hash"],
    )
