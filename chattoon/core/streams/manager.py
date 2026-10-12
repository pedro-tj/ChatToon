"""Runs every enabled source at the same time, each in its own task.

The manager owns no platform knowledge: it starts, stops and restarts connectors,
keeps one status and a few counters per source, and forwards messages to the engine.
Sources can be added, edited, disabled or reconnected while the stream is running; only
the affected task changes. One source crashing never touches the others.
"""

from __future__ import annotations

import asyncio
import importlib
import logging
import time
from collections import deque
from collections.abc import Callable
from dataclasses import asdict, dataclass, field

from ..config import SourceConfig
from ..messages import ChatMessage
from .base import ACTIVE_STATES, Connector, ConnectorContext, ProbeResult, SourceStatus

log = logging.getLogger(__name__)

# platform -> "module:Class" (imported on first use, so optional libraries stay optional)
CONNECTORS = {
    "youtube": "youtube:YouTubeConnector",
    "twitch": "twitch:TwitchConnector",
    "kick": "kick:KickConnector",
    "tiktok": "tiktok:TikTokConnector",
    "facebook": "meta:FacebookConnector",
    "instagram": "meta:InstagramConnector",
    "x": "x:XConnector",
}


def connector_class(platform: str) -> type[Connector]:
    module, _, name = CONNECTORS[platform].partition(":")
    return getattr(importlib.import_module(f"{__package__}.{module}"), name)


@dataclass
class SourceStats:
    received: int = 0
    queued: int = 0
    answered: int = 0
    dropped: int = 0
    last_message: float = 0.0
    recent: deque = field(default_factory=lambda: deque(maxlen=600))  # arrival times (rate)

    def rate(self, now: float) -> int:
        """Messages in the last minute."""
        while self.recent and now - self.recent[0] > 60:
            self.recent.popleft()
        return len(self.recent)


class MultiStreamManager:
    def __init__(self, on_message: Callable[[ChatMessage], None], on_change: Callable[[], None],
                 ctx: ConnectorContext | None = None, factories: dict[str, Callable] | None = None,
                 on_retract: Callable[[str, str, str], None] | None = None):
        self.on_message = on_message
        self.on_retract = on_retract or (lambda source_id, message_id, author_id: None)
        self.on_change = on_change  # statuses or counters changed (the engine throttles UI updates)
        self.ctx = ctx or ConnectorContext()
        self.factories = factories or {}  # platform -> connector factory (tests)
        self.sources: dict[str, SourceConfig] = {}
        self.statuses: dict[str, SourceStatus] = {}
        self.stats: dict[str, SourceStats] = {}
        self._tasks: dict[str, asyncio.Task] = {}
        self._connectors: dict[str, Connector] = {}
        self._signature: dict[str, tuple] = {}
        self.held: set[str] = set()  # disconnected by hand for this session (still enabled)
        self.running = False

    # -- configuration -------------------------------------------------------

    def configure(self, sources: list[SourceConfig]) -> None:
        """Adopt the configured sources; while running, (re)start or stop what changed."""
        wanted = {s.id: s for s in sources}
        for sid in list(self.sources):
            if sid not in wanted:
                self._cancel(sid)
                self.sources.pop(sid, None)
                self.statuses.pop(sid, None)
                self.stats.pop(sid, None)
                self.held.discard(sid)
        for sid, source in wanted.items():
            signature = (source.platform, source.target, tuple(sorted(source.options.items())))
            changed = self._signature.get(sid) != signature
            self.sources[sid] = source
            self._signature[sid] = signature
            self.stats.setdefault(sid, SourceStats())
            status = self.statuses.setdefault(sid, SourceStatus(sid, source.platform))
            status.platform = source.platform
            if not source.enabled:
                self._cancel(sid)
                self._set(sid, "disabled")
            elif self.running and sid not in self.held and (changed or status.state in ("disabled", "idle")):
                # sources stopped on purpose (login revoked, live ended…) wait for Connect or a new login
                self._start(sid)
            elif not self.running and status.state == "disabled":
                self._set(sid, "idle")
        self.on_change()

    def _alive(self, sid: str) -> bool:
        task = self._tasks.get(sid)
        return bool(task and not task.done())

    def _set(self, sid: str, state: str, code: str = "", detail: str = "") -> None:
        status = self.statuses[sid]
        if status.state != state:
            status.since = time.time()
        status.state, status.code, status.detail, status.retry_in = state, code, detail, 0.0

    # -- lifecycle -------------------------------------------------------------

    def start(self) -> None:
        self.running = True
        self.held.clear()
        for sid, source in self.sources.items():
            if source.enabled:
                self._start(sid)
        self.on_change()

    async def stop(self) -> None:
        self.running = False
        tasks = [self._cancel(sid) for sid in list(self._tasks)]
        await asyncio.gather(*(t for t in tasks if t), return_exceptions=True)
        for sid, source in self.sources.items():
            self._set(sid, "idle" if source.enabled else "disabled")
        self.on_change()

    def connect(self, sid: str) -> None:
        """Connect (or reconnect) one source now, even if it was disconnected by hand."""
        if sid not in self.sources or not self.sources[sid].enabled:
            return
        self.held.discard(sid)
        if self.running:
            self._start(sid)
        self.on_change()

    def disconnect(self, sid: str) -> None:
        if sid in self.sources:
            self.held.add(sid)
            self._cancel(sid)
            self._set(sid, "stopped")
            self.on_change()

    def _start(self, sid: str) -> None:
        self._cancel(sid)
        source = self.sources[sid]
        try:
            connector = self._build(source)
        except Exception as e:  # noqa: BLE001 - a bad source must never break the others
            code = "invalid" if isinstance(e, ValueError) else "unsupported" if isinstance(e, ImportError) else "error"
            self._set(sid, "error" if code != "unsupported" else "unsupported", code, str(e)[:300])
            log.warning("source %s cannot start: %s", sid, e)
            return
        self._connectors[sid] = connector
        self._tasks[sid] = asyncio.create_task(self._run(sid, connector), name=f"chattoon-source-{sid}")

    def _build(self, source: SourceConfig) -> Connector:
        factory = self.factories.get(source.platform) or connector_class(source.platform)
        connector = factory(source, self._deliver, self._status, self.ctx)
        connector.on_retract = self.on_retract
        return connector

    async def _run(self, sid: str, connector: Connector) -> None:
        try:
            await connector.run()
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001 - isolated: report and keep the others going
            log.exception("source %s crashed", sid)
            if sid in self.statuses and self._connectors.get(sid) is connector:
                self._set(sid, "error", "crashed", f"{type(e).__name__}: {e}"[:300])
                self.on_change()

    def _cancel(self, sid: str) -> asyncio.Task | None:
        task = self._tasks.pop(sid, None)
        self._connectors.pop(sid, None)
        if task and not task.done():
            task.cancel()
            return task
        return None

    # -- callbacks from connectors ----------------------------------------------

    def _status(self, status: SourceStatus) -> None:
        sid = status.source_id
        connector = self._connectors.get(sid)
        if sid not in self.statuses or connector is None or connector.status is not status:
            return  # a cancelled connector reporting late
        current = self.statuses[sid]
        for name in ("state", "code", "detail", "attempt", "channel", "since", "retry_in"):
            setattr(current, name, getattr(status, name))
        self.on_change()

    def _deliver(self, msg: ChatMessage) -> None:
        stats = self.stats.get(msg.source_id)
        if stats is None:
            return  # source removed while a message was in flight
        now = time.monotonic()
        stats.received += 1
        stats.last_message = time.time()
        stats.recent.append(now)
        self.on_message(msg)

    # -- queries -----------------------------------------------------------------

    async def probe(self, source: SourceConfig, timeout: float = 25) -> ProbeResult:
        try:
            connector = self._build(source)
        except ValueError as e:
            return ProbeResult(False, "invalid", str(e))
        except ImportError as e:
            return ProbeResult(False, "unsupported", str(e))
        try:
            return await asyncio.wait_for(connector.probe(), timeout)
        except asyncio.TimeoutError:
            return ProbeResult(False, "timeout")
        except Exception as e:  # noqa: BLE001 - reported to the streamer
            code = getattr(e, "code", "error")
            return ProbeResult(False, code, str(e)[:300])
        finally:
            await connector.close()

    def connected_platforms(self) -> set[str]:
        return {self.sources[s].platform for s, st in self.statuses.items()
                if st.state == "connected" and s in self.sources}

    def active_count(self) -> int:
        return sum(1 for st in self.statuses.values() if st.state in ACTIVE_STATES)

    def snapshot(self) -> list[dict]:
        now = time.monotonic()
        out = []
        for sid, source in self.sources.items():
            stats = self.stats[sid]
            out.append(dict(
                asdict(source), status=self.statuses[sid].to_dict(), held=sid in self.held,
                received=stats.received, answered=stats.answered, dropped=stats.dropped, queued=stats.queued,
                rate=stats.rate(now), lastMessage=stats.last_message,
            ))
        return out

    def aggregate_state(self) -> str:
        """One word for the old single-chat status (dashboard, CLI)."""
        states = [st.state for sid, st in self.statuses.items() if self.sources.get(sid, None) and self.sources[sid].enabled]
        for state in ("connected", "reconnecting", "connecting", "waiting", "auth_required", "error", "ended"):
            if state in states:
                return state
        return "stopped"
