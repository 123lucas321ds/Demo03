"""JSONL session storage with legal tool-call boundary trimming."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class Session:
    """A single append-only message session."""

    key: str
    messages: list[dict[str, Any]] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    last_consolidated: int = 0

    def append_messages(self, messages: list[dict[str, Any]]) -> None:
        self.messages.extend(dict(message) for message in messages)
        self.updated_at = datetime.now().isoformat()

    @staticmethod
    def _find_legal_start(messages: list[dict[str, Any]]) -> int:
        """Find a suffix where every tool result has a matching assistant tool_call."""

        declared: set[str] = set()
        start = 0
        for index, message in enumerate(messages):
            role = message.get("role")
            if role == "assistant":
                for tool_call in message.get("tool_calls") or []:
                    if isinstance(tool_call, dict) and tool_call.get("id"):
                        declared.add(str(tool_call["id"]))
            elif role == "tool":
                tool_call_id = message.get("tool_call_id")
                if tool_call_id and str(tool_call_id) not in declared:
                    start = index + 1
                    declared.clear()
                    for previous in messages[start:index + 1]:
                        if previous.get("role") == "assistant":
                            for tool_call in previous.get("tool_calls") or []:
                                if isinstance(tool_call, dict) and tool_call.get("id"):
                                    declared.add(str(tool_call["id"]))
        return start

    def get_history(self, max_messages: int = 500) -> list[dict[str, Any]]:
        """Return unconsolidated history without orphan tool results."""

        history = self.messages[self.last_consolidated:]
        if max_messages > 0:
            history = history[-max_messages:]

        for index, message in enumerate(history):
            if message.get("role") == "user":
                history = history[index:]
                break

        legal_start = self._find_legal_start(history)
        if legal_start:
            history = history[legal_start:]

        return [self._history_entry(message) for message in history]

    @staticmethod
    def _history_entry(message: dict[str, Any]) -> dict[str, Any]:
        entry = {"role": message["role"], "content": message.get("content")}
        for key in ("tool_calls", "tool_call_id", "name"):
            if key in message:
                entry[key] = message[key]
        return entry


class SessionManager:
    """Persist sessions as JSONL files."""

    def __init__(self, sessions_dir: Path) -> None:
        self.sessions_dir = sessions_dir
        self.sessions_dir.mkdir(parents=True, exist_ok=True)

    def path_for(self, key: str) -> Path:
        safe = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in key)
        return self.sessions_dir / f"{safe}.jsonl"

    def save(self, session: Session) -> None:
        path = self.path_for(session.key)
        metadata = {
            "_type": "metadata",
            "key": session.key,
            "created_at": session.created_at,
            "updated_at": session.updated_at,
            "last_consolidated": session.last_consolidated,
        }
        temp_path = path.with_suffix(".jsonl.tmp")
        with temp_path.open("w", encoding="utf-8") as handle:
            handle.write(json.dumps(metadata, ensure_ascii=False) + "\n")
            for message in session.messages:
                handle.write(json.dumps(message, ensure_ascii=False) + "\n")
        temp_path.replace(path)

    def load(self, key: str) -> Session | None:
        path = self.path_for(key)
        if not path.exists():
            return None

        messages: list[dict[str, Any]] = []
        metadata: dict[str, Any] = {}
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                data = json.loads(line)
                if data.get("_type") == "metadata":
                    metadata = data
                else:
                    messages.append(data)

        return Session(
            key=metadata.get("key", key),
            messages=messages,
            created_at=metadata.get("created_at", datetime.now().isoformat()),
            updated_at=metadata.get("updated_at", datetime.now().isoformat()),
            last_consolidated=int(metadata.get("last_consolidated", 0)),
        )
