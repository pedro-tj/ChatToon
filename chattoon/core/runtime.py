"""Runs the asyncio engine in its own thread so the Qt interface never blocks."""

from __future__ import annotations

import asyncio
import concurrent.futures
import threading
from collections.abc import Coroutine


class Runtime:
    def __init__(self) -> None:
        self.loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run, name="chattoon-engine", daemon=True)
        self._ready = threading.Event()

    def _run(self) -> None:
        asyncio.set_event_loop(self.loop)
        self.loop.call_soon(self._ready.set)
        self.loop.run_forever()

    def start(self) -> None:
        self._thread.start()
        self._ready.wait(5)

    def submit(self, coro: Coroutine) -> concurrent.futures.Future:
        return asyncio.run_coroutine_threadsafe(coro, self.loop)

    def run(self, coro: Coroutine, timeout: float | None = 30):
        return self.submit(coro).result(timeout)

    def stop(self, shutdown: Coroutine | None = None, timeout: float = 5) -> None:
        if not self._thread.is_alive():
            return
        if shutdown is not None:
            try:
                self.run(shutdown, timeout)
            except Exception:  # noqa: BLE001 - best effort on exit
                pass
        self.loop.call_soon_threadsafe(self.loop.stop)
        self._thread.join(timeout)
