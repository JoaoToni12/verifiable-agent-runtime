import os
from dataclasses import dataclass
from pathlib import Path

from verifiable_agent_runtime.models import RuntimeMode


@dataclass(frozen=True, slots=True)
class Settings:
    database_path: Path
    mode: RuntimeMode

    @classmethod
    def from_environment(cls) -> "Settings":
        database = Path(os.getenv("AGENT_RUNTIME_DATABASE", "runtime.sqlite3"))
        raw_mode = os.getenv("AGENT_RUNTIME_MODE", RuntimeMode.SHADOW.value)
        return cls(database_path=database, mode=RuntimeMode(raw_mode))
