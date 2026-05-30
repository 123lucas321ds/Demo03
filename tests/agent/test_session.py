from __future__ import annotations

from sc2_agent.agent.session import Session, SessionManager


def _tool_turn(prefix: str) -> list[dict]:
    return [
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {"id": f"{prefix}_a", "type": "function", "function": {"name": "x", "arguments": {}}},
                {"id": f"{prefix}_b", "type": "function", "function": {"name": "y", "arguments": {}}},
            ],
        },
        {"role": "tool", "tool_call_id": f"{prefix}_a", "name": "x", "content": "ok"},
        {"role": "tool", "tool_call_id": f"{prefix}_b", "name": "y", "content": "ok"},
    ]


def _assert_no_orphans(history: list[dict]) -> None:
    declared = {
        tool_call["id"]
        for message in history
        if message.get("role") == "assistant"
        for tool_call in message.get("tool_calls") or []
    }
    orphans = [
        message.get("tool_call_id")
        for message in history
        if message.get("role") == "tool" and message.get("tool_call_id") not in declared
    ]
    assert orphans == []


def test_session_history_trims_orphan_tool_results() -> None:
    session = Session(key="game")
    session.messages.append({"role": "tool", "tool_call_id": "missing", "name": "x", "content": "orphan"})
    session.messages.append({"role": "user", "content": "fresh"})
    session.messages.extend(_tool_turn("fresh"))

    history = session.get_history(max_messages=10)

    _assert_no_orphans(history)
    assert history[0]["role"] == "user"
    assert history[0]["content"] == "fresh"


def test_session_history_respects_last_consolidated() -> None:
    session = Session(key="game")
    session.messages.append({"role": "user", "content": "old"})
    session.messages.append({"role": "assistant", "content": "old answer"})
    session.messages.append({"role": "user", "content": "new"})
    session.messages.append({"role": "assistant", "content": "new answer"})
    session.last_consolidated = 2

    history = session.get_history(max_messages=10)

    assert [message["content"] for message in history] == ["new", "new answer"]


def test_session_manager_roundtrip(tmp_path) -> None:
    manager = SessionManager(tmp_path)
    session = Session(key="game:one")
    session.messages.append({"role": "user", "content": "hello"})
    session.last_consolidated = 1

    manager.save(session)
    loaded = manager.load("game:one")

    assert loaded is not None
    assert loaded.key == "game:one"
    assert loaded.messages == [{"role": "user", "content": "hello"}]
    assert loaded.last_consolidated == 1
