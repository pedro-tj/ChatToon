"""Tiny synchronous event bus (events are emitted from the engine's asyncio thread)."""

from __future__ import annotations

import logging
from collections.abc import Callable

log = logging.getLogger(__name__)

Listener = Callable[[str, dict], None]


class EventBus:
    def __init__(self) -> None:
        self._listeners: list[Listener] = []

    def subscribe(self, listener: Listener) -> Callable[[], None]:
        self._listeners.append(listener)
        return lambda: self._listeners.remove(listener) if listener in self._listeners else None

    def emit(self, kind: str, data: dict | None = None) -> None:
        payload = data or {}
        for listener in list(self._listeners):
            try:
                listener(kind, payload)
            except Exception:  # a broken listener must never stop the engine
                log.exception("event listener failed for %s", kind)
