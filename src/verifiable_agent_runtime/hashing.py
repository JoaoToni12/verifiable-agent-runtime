import hashlib
import json
from collections.abc import Mapping
from typing import Any


def canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def payload_digest(payload: Mapping[str, Any]) -> str:
    return sha256_text(canonical_json(payload))


def event_digest(event: Mapping[str, Any]) -> str:
    return sha256_text(canonical_json(event))
