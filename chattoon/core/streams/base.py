"""Connector contract shared by every streaming platform.

A connector reads ONE source (a YouTube live, a Twitch channel, a TikTok profile…) and
turns whatever the platform sends into :class:`ChatMessage` objects. Each source runs in
its own asyncio task under :meth:`Connector.run`, which owns the reconnection policy:

* ``session()`` is one connection lifetime, implemented by each platform. It returns when
  the live ended and raises :class:`ConnectorError` subclasses for everything else;
* transient failures (network, timeouts, 5xx) back off exponentially with full jitter,
  capped, and the counter resets after a connection that stayed up for a while;
* "not live yet" polls slowly (never faster than ``WAIT_POLL`` seconds);
* rate limits wait for what the platform asked (``Retry-After``);
* authentication problems and unsupported setups stop the source and say why — retrying
  a revoked token would only hammer the platform.

A failure in one source never reaches the others: the manager runs each in its own task.
"""

from __future__ import annotations

import asyncio
import logging
import random
import time
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import ClassVar

import aiohttp

from ..config import SourceConfig
from ..messages import ChatMessage

log = logging.getLogger(__name__)

# connected: reading · waiting: channel offline / live not started (polls slowly)
STATES = ("idle", "connecting", "connected", "reconnecting", "waiting", "ended", "auth_required", "error",
          "unsupported", "stopped", "disabled")
WAIT_POLL = 60.0  # seconds between "is it live now?" checks

# support levels shown to the streamer, decided from evidence (docs/14-platform-api-research.md)
SUPPORT = ("functional", "limited", "experimental", "unavailable")


class ConnectorError(Exception):
    """Base error. ``code`` is stable (the interface translates it); ``str()`` is detail."""

    code = "error"
    retry = True

    def __init__(self, message: str = "", code: str = ""):
        super().__init__(message)
        if code:
            self.code = code


class TransientError(ConnectorError):
    code = "network"


class RateLimited(ConnectorError):
    code = "rate-limited"

    def __init__(self, message: str = "", retry_after: float = 60.0):
        super().__init__(message)
        self.retry_after = retry_after


class NotLive(ConnectorError):
    """The channel exists but is not broadcasting (yet). Checked again later."""

    code = "not-live"


class LiveEnded(ConnectorError):
    code = "ended"
    retry = False


class AuthRequired(ConnectorError):
    code = "auth-required"
    retry = False


class Unsupported(ConnectorError):
    """Missing optional dependency, missing developer app or a platform without an API."""

    code = "unsupported"
    retry = False


class FatalError(ConnectorError):
    """Bad URL, channel not found, chat disabled: retrying cannot help."""

    code = "fatal"
    retry = False


@dataclass
class SourceStatus:
    source_id: str
    platform: str
    state: str = "idle"
    code: str = ""  # machine readable reason (ConnectorError.code)
    detail: str = ""  # technical detail, never contains credentials
    attempt: int = 0
    channel: str = ""  # resolved display name (e.g. the Twitch display name)
    since: float = field(default_factory=time.time)
    retry_in: float = 0.0

    def to_dict(self) -> dict:
        return {"id": self.source_id, "platform": self.platform, "state": self.state, "code": self.code,
                "detail": self.detail, "attempt": self.attempt, "channel": self.channel, "since": self.since,
                "retryIn": round(self.retry_in, 1)}


@dataclass
class ProbeResult:
    """Outcome of "Test connection" (no messages are read)."""

    ok: bool
    code: str = ""  # live | offline | auth-required | not-found | unsupported | network | invalid | …
    detail: str = ""
    channel: str = ""

    def to_dict(self) -> dict:
        return {"ok": self.ok, "code": self.code, "detail": self.detail, "channel": self.channel}


@dataclass
class StreamMetadata:
    """Public information about a source's channel and current live (Stream context › AI).

    Platforms differ a lot: each connector fills only what its official API (or the
    endpoint it already uses to read the chat) really provides, and says how it got it.
    Nothing is guessed; a field the platform does not provide stays empty."""

    source_id: str
    platform: str
    ok: bool = True
    code: str = "found"  # found | offline | unavailable | auth-required | not-found | network | error
    detail: str = ""
    method: str = ""  # how it was read, shown to the streamer (e.g. "YouTube oEmbed (official)")
    live: bool | None = None
    channel: str = ""
    title: str = ""
    description: str = ""
    category: str = ""
    tags: list[str] = field(default_factory=list)
    url: str = ""
    fetched_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {"sourceId": self.source_id, "platform": self.platform, "ok": self.ok, "code": self.code,
                "detail": self.detail[:300], "method": self.method, "live": self.live, "channel": self.channel[:120],
                "title": self.title[:300], "description": self.description[:1500], "category": self.category[:120],
                "tags": [str(t)[:40] for t in self.tags[:20]], "url": self.url[:300], "fetchedAt": self.fetched_at}


@dataclass
class ConnectorContext:
    """What connectors may use from the application (injected, so tests can fake it)."""

    credentials: object = None  # credentials.CredentialStore
    apps: object = None  # config.PlatformApps
    skip_backlog: bool = True
    open_browser: Callable[[str], None] = lambda url: None
    notify: Callable[[str, dict], None] = lambda kind, data: None  # e.g. device-code prompts
    user_agent: str = "ChatToon (+https://github.com/ruscher/ChatToon)"
    extra: dict = field(default_factory=dict)  # test hooks: base URLs, factories


class Backoff:
    """Exponential backoff with full jitter: random(0.5·d, d) where d doubles up to ``cap``."""

    def __init__(self, base: float = 2.0, cap: float = 120.0, rng: random.Random | None = None):
        self.base, self.cap, self.rng = base, cap, rng or random.Random()
        self.attempt = 0

    def next(self) -> float:
        self.attempt += 1
        ceiling = min(self.cap, self.base * 2 ** min(self.attempt - 1, 12))
        return self.rng.uniform(ceiling / 2, ceiling)

    def reset(self) -> None:
        self.attempt = 0


class Connector:
    """Base class. Subclasses set the class attributes and implement :meth:`session`."""

    platform: ClassVar[str] = ""
    label: ClassVar[str] = ""
    support: ClassVar[str] = "functional"
    stable_after: ClassVar[float] = 60.0  # a connection this old resets the backoff
    reconnect_when_ended: ClassVar[bool] = False  # channel-based sources wait for the next live
    wait_poll: ClassVar[float] = WAIT_POLL  # seconds between "live now?" checks while waiting

    def __init__(self, source: SourceConfig, on_message: Callable[[ChatMessage], None],
                 on_status: Callable[[SourceStatus], None], ctx: ConnectorContext | None = None):
        self.source = source
        self.ctx = ctx or ConnectorContext()
        self._on_message = on_message
        self._on_status = on_status
        self.status = SourceStatus(source.id, self.platform)
        self.backoff = Backoff(rng=self.ctx.extra.get("rng"))
        self._seen: OrderedDict[str, None] = OrderedDict()
        self.received = 0
        self._sleep = self.ctx.extra.get("sleep", asyncio.sleep)
        # moderation: (message_id, author_id) removed by the channel's moderators
        self.on_retract: Callable[[str, str, str], None] = lambda source_id, message_id, author_id: None

    # -- helpers for subclasses --------------------------------------------

    def set_status(self, state: str, code: str = "", detail: str = "", retry_in: float = 0.0) -> None:
        if state != self.status.state:
            self.status.since = time.time()
        self.status.state, self.status.code, self.status.detail = state, code, detail[:300]
        self.status.attempt, self.status.retry_in = self.backoff.attempt, retry_in
        self._on_status(self.status)

    def connected(self, channel: str = "") -> None:
        if channel:
            self.status.channel = channel
        self.set_status("connected")

    def emit(self, msg: ChatMessage) -> None:
        """Deliver one message once (ids are de-duplicated per source)."""
        if not msg.id or msg.id in self._seen:
            return
        self._seen[msg.id] = None
        if len(self._seen) > 5000:
            self._seen.popitem(last=False)
        msg.platform = self.platform
        msg.source_id = self.source.id
        msg.channel = msg.channel or self.status.channel or self.source.label or self.source.target
        self.received += 1
        self._on_message(msg)

    def retract(self, message_id: str = "", author_id: str = "") -> None:
        """A moderator deleted a message (or every message of a viewer): never read it."""
        self.on_retract(self.source.id, message_id, author_id)

    def remember(self, message_id: str) -> None:
        """Mark a message as seen without delivering it (backlog skipped on connect)."""
        self._seen[message_id] = None

    # -- contract ----------------------------------------------------------

    async def session(self) -> None:
        """One connection lifetime: read until the live ends (return) or raise."""
        raise NotImplementedError

    async def probe(self) -> ProbeResult:
        """Check the source without reading messages (the "Test connection" button)."""
        return ProbeResult(True, "unknown")

    async def metadata(self) -> StreamMetadata:
        """Title, description, category… of the channel and its live, when the platform
        offers a sanctioned way to read them. The default: it does not."""
        return StreamMetadata(self.source.id, self.platform, ok=False, code="unavailable",
                              detail="This platform offers ChatToon no way to read the live's title or description.")

    async def close(self) -> None:
        """Release resources (called when the task stops, also on cancellation)."""

    # -- supervisor ----------------------------------------------------------

    async def run(self) -> None:
        """Keep the source connected until it is stopped, ended or cannot work."""
        try:
            while True:
                started = time.monotonic()
                self.set_status("connecting" if self.backoff.attempt == 0 else "reconnecting")
                try:
                    await self.session()
                    if not self.reconnect_when_ended:
                        self.set_status("ended", "ended")
                        return
                    raise NotLive("The live ended; waiting for the next one.")
                except asyncio.CancelledError:
                    raise
                except NotLive as e:
                    self.backoff.reset()
                    wait = float(self.ctx.extra.get("wait_poll", self.wait_poll))
                    self.set_status("waiting", e.code, str(e), wait)
                    await self._sleep(wait)
                except RateLimited as e:
                    wait = max(5.0, min(900.0, e.retry_after))
                    self.set_status("reconnecting", e.code, str(e), wait)
                    await self._sleep(wait)
                except LiveEnded as e:
                    self.set_status("ended", e.code, str(e))
                    return
                except AuthRequired as e:
                    self.set_status("auth_required", e.code, str(e))
                    return
                except Unsupported as e:
                    self.set_status("unsupported", e.code, str(e))
                    return
                except ConnectorError as e:
                    if not e.retry:
                        self.set_status("error", e.code, str(e))
                        return
                    await self._retry(started, e.code, str(e))
                except (aiohttp.ClientError, OSError, asyncio.TimeoutError, ValueError, KeyError, TypeError) as e:
                    # network trouble, HTTP errors and a platform's odd payloads are all worth a retry
                    log.warning("%s source %s: %s", self.platform, self.source.id, type(e).__name__)
                    await self._retry(started, "network", f"{type(e).__name__}: {e}")
        except asyncio.CancelledError:
            self.set_status("stopped")
            raise
        finally:
            try:
                await asyncio.shield(self.close())
            except Exception:  # noqa: BLE001 - closing must not hide the real outcome
                log.debug("close failed", exc_info=True)

    async def _retry(self, started: float, code: str, detail: str) -> None:
        if time.monotonic() - started >= self.stable_after:
            self.backoff.reset()
        delay = self.backoff.next()
        self.set_status("reconnecting", code, detail, delay)
        await self._sleep(delay)


def retry_after(headers, default: float = 60.0) -> float:
    """Seconds from a Retry-After / Ratelimit-Reset header."""
    for name in ("Retry-After", "Ratelimit-Reset", "X-RateLimit-Reset", "x-rate-limit-reset"):
        value = headers.get(name) if headers else None
        if not value:
            continue
        try:
            number = float(value)
        except ValueError:
            continue
        return max(1.0, number - time.time()) if number > 1e9 else max(1.0, number)
    return default
