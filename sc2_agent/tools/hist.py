"""History query tools."""

from __future__ import annotations

from typing import Any

from sc2_agent.history.store import EventStore, SnapshotRecorder
from sc2_agent.tools.base import Tool


class HistSnapshotTool(Tool):
    def __init__(self, recorder: SnapshotRecorder) -> None:
        self.recorder = recorder

    @property
    def name(self) -> str:
        return "hist.snapshot"

    @property
    def description(self) -> str:
        return "Load a snapshot by kind and index."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {"kind": {"type": ["string", "null"]}, "index": {"type": "integer"}},
        }

    async def execute(self, **kwargs: Any) -> Any:
        try:
            return self.recorder.load(kind=kwargs.get("kind"), index=int(kwargs.get("index", -1)))
        except (IndexError, FileNotFoundError) as exc:
            return {"ok": False, "code": "SNAPSHOT_NOT_FOUND", "error": str(exc)}


class HistTrendTool(Tool):
    def __init__(self, recorder: SnapshotRecorder) -> None:
        self.recorder = recorder

    @property
    def name(self) -> str:
        return "hist.trend"

    @property
    def description(self) -> str:
        return "Return metric values from recent snapshots."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {"metric": {"type": "string"}, "lookback_n": {"type": "integer", "minimum": 1}},
            "required": ["metric"],
        }

    async def execute(self, **kwargs: Any) -> Any:
        return {"metric": kwargs["metric"], "points": self.recorder.values(metric=kwargs["metric"], lookback_n=int(kwargs.get("lookback_n", 5)))}


class HistUnitTool(Tool):
    def __init__(self, recorder: SnapshotRecorder) -> None:
        self.recorder = recorder

    @property
    def name(self) -> str:
        return "hist.unit"

    @property
    def description(self) -> str:
        return "Return appearances of a unit tag across snapshots."

    @property
    def parameters(self) -> dict[str, Any]:
        return {"type": "object", "properties": {"tag": {"type": "integer"}}, "required": ["tag"]}

    async def execute(self, **kwargs: Any) -> Any:
        tag = int(kwargs["tag"])
        matches: list[dict[str, Any]] = []
        for row in self.recorder.list(kind=None):
            try:
                snapshot = self.recorder.load(index=int(row["index"]))
            except (IndexError, FileNotFoundError):
                continue
            payload = snapshot["payload"]
            entities = [*(payload.get("units") or []), *(payload.get("structures") or [])]
            for entity in entities:
                if int(entity.get("tag", -1)) == tag:
                    matches.append({"game_time": row["game_time"], "entity": entity})
        return {"tag": tag, "matches": matches}


class HistCompareTool(Tool):
    def __init__(self, recorder: SnapshotRecorder) -> None:
        self.recorder = recorder

    @property
    def name(self) -> str:
        return "hist.compare"

    @property
    def description(self) -> str:
        return "Compare two snapshots by index."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {"index_a": {"type": "integer"}, "index_b": {"type": "integer"}},
            "required": ["index_a", "index_b"],
        }

    async def execute(self, **kwargs: Any) -> Any:
        try:
            a = self.recorder.load(index=int(kwargs["index_a"]))
            b = self.recorder.load(index=int(kwargs["index_b"]))
        except (IndexError, FileNotFoundError) as exc:
            return {"ok": False, "code": "SNAPSHOT_NOT_FOUND", "error": str(exc)}
        return {"a": a, "b": b, "changed": a["payload"] != b["payload"]}


class HistEventsTool(Tool):
    def __init__(self, event_store: EventStore) -> None:
        self._store = event_store

    @property
    def name(self) -> str:
        return "hist.events"

    @property
    def description(self) -> str:
        return "Query recent events by type and optional time range."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "event_type": {"type": ["string", "null"]},
                "since_game_time": {"type": ["number", "null"]},
                "limit": {"type": ["integer", "null"]},
            },
        }

    async def execute(self, **kwargs: Any) -> Any:
        events = self._store.query(
            event_type=kwargs.get("event_type"),
            since_game_time=kwargs.get("since_game_time"),
            limit=kwargs.get("limit"),
        )
        return {"events": events, "count": len(events)}
