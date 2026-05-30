"""Observation providers used by tools and tests."""

from __future__ import annotations

from typing import Protocol

from sc2_agent.observation.models import ObservationSnapshot


class ObservationProvider(Protocol):
    def snapshot(self) -> ObservationSnapshot:
        """Return the latest normalized observation."""


class StaticObservationProvider:
    def __init__(self, snapshot: ObservationSnapshot) -> None:
        self._snapshot = snapshot

    def snapshot(self) -> ObservationSnapshot:
        return self._snapshot


class ObservationStore:
    """Mutable in-memory observation store for early integration tests."""

    def __init__(self, snapshot: ObservationSnapshot) -> None:
        self._snapshot = snapshot

    def update(self, snapshot: ObservationSnapshot) -> None:
        self._snapshot = snapshot

    def snapshot(self) -> ObservationSnapshot:
        return self._snapshot
