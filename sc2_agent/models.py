"""Common result models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class Result:
    """Generic structured result used by early infrastructure code."""

    ok: bool
    data: Any = None
    error: str | None = None
    code: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def success(cls, data: Any = None, **meta: Any) -> "Result":
        return cls(ok=True, data=data, meta=dict(meta))

    @classmethod
    def failure(cls, code: str, error: str, **meta: Any) -> "Result":
        return cls(ok=False, code=code, error=error, meta=dict(meta))
