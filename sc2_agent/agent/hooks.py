"""Lifecycle hooks — extension points for logging and instrumentation."""

from __future__ import annotations

from typing import Any, Callable

Hook = Callable[..., None]


class LifecycleHooks:
    """Collect and invoke callbacks for agent lifecycle events.

    Hooks do NOT affect control flow. They are fire-and-forget observers.
    """

    def __init__(self) -> None:
        self._on_wake: list[Hook] = []
        self._on_tool_call: list[Hook] = []
        self._on_commit: list[Hook] = []
        self._on_abort: list[Hook] = []
        self._on_sleep: list[Hook] = []
        self._on_error: list[Hook] = []

    # --- registration ---

    def on_wake(self, fn: Hook) -> Hook:
        self._on_wake.append(fn)
        return fn

    def on_tool_call(self, fn: Hook) -> Hook:
        self._on_tool_call.append(fn)
        return fn

    def on_commit(self, fn: Hook) -> Hook:
        self._on_commit.append(fn)
        return fn

    def on_abort(self, fn: Hook) -> Hook:
        self._on_abort.append(fn)
        return fn

    def on_sleep(self, fn: Hook) -> Hook:
        self._on_sleep.append(fn)
        return fn

    def on_error(self, fn: Hook) -> Hook:
        self._on_error.append(fn)
        return fn

    # --- fire ---

    def fire_wake(self, **kwargs: Any) -> None:
        for fn in self._on_wake:
            _safe_call(fn, **kwargs)

    def fire_tool_call(self, **kwargs: Any) -> None:
        for fn in self._on_tool_call:
            _safe_call(fn, **kwargs)

    def fire_commit(self, **kwargs: Any) -> None:
        for fn in self._on_commit:
            _safe_call(fn, **kwargs)

    def fire_abort(self, **kwargs: Any) -> None:
        for fn in self._on_abort:
            _safe_call(fn, **kwargs)

    def fire_sleep(self, **kwargs: Any) -> None:
        for fn in self._on_sleep:
            _safe_call(fn, **kwargs)

    def fire_error(self, **kwargs: Any) -> None:
        for fn in self._on_error:
            _safe_call(fn, **kwargs)


def _safe_call(fn: Hook, **kwargs: Any) -> None:
    try:
        fn(**kwargs)
    except Exception:
        pass
