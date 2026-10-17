"""Base of the interface's feature controllers (AI centre, voices, connectivity…).

Each controller is a QObject owned by the Backend and reached from QML as ``backend.<name>``.
Work runs on the engine's asyncio loop (never on the GUI thread); results come back to the
GUI thread through ``later()``.
"""

from __future__ import annotations

import concurrent.futures
import logging

from PySide6.QtCore import QObject, Signal

log = logging.getLogger(__name__)


class Controller(QObject):
    _call = Signal(object)  # a function to run on the GUI thread

    def __init__(self, backend) -> None:
        super().__init__(backend)
        self.backend = backend
        self._call.connect(lambda fn: fn())

    @property
    def settings(self):
        return self.backend.settings

    @property
    def engine(self):
        return self.backend.engine

    def later(self, fn) -> None:
        """Run ``fn`` on the GUI thread (safe from the engine thread)."""
        if not self.backend._closing:
            self._call.emit(fn)

    def submit(self, coro) -> concurrent.futures.Future:
        future = self.backend.runtime.submit(coro)
        future.add_done_callback(self._log_failure)
        return future

    @staticmethod
    def _log_failure(future: concurrent.futures.Future) -> None:
        if not future.cancelled() and future.exception() is not None:
            log.error("background task failed", exc_info=future.exception())

    def toast(self, message: str, kind: str = "info") -> None:
        self.later(lambda: self.backend.notify(message, kind))
