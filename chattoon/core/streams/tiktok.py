"""TikTok LIVE comments, gifts, follows and subscriptions (experimental, unofficial).

TikTok offers NO official API to read the comments of a LIVE. The only route is the
community library TikTokLive (https://github.com/isaackogan/TikTokLive, pinned 7.0.1),
which reverse-engineers TikTok's web player. Say it plainly to the streamer:

* it is unofficial: TikTok may change its protocol, block it or break it at any time,
  and nothing here is endorsed by TikTok;
* it depends on a third-party service, **Euler Stream** (https://api.eulerstream.com),
  that signs the WebSocket connection. Each connection start sends Euler Stream the room
  id, a browser User-Agent, the client name (``ttlive-python``), the platform ("web"),
  the default data-centre cookie and the streamer's network address; with an optional
  API key, also that key (``X-Api-Key``). No TikTok login is ever sent (ChatToon never
  sets a session id). Checking "is it live?" talks to tiktok.com only;
* Euler Stream's free community tier is rate limited (a few thousand requests a day);
  when it says "slow down" the source waits what it asked, then retries. A personal API
  key (credential ``tiktok/sign`` -> ``{"api_key": "…"}``, kept in the keyring, never
  logged nor shown) raises that limit;
* the library itself turns TLS verification OFF for Euler Stream; ChatToon turns it back
  on before the first request (source option ``sign_tls=library`` restores the default);
* license: TikTokLive is "Modified AGPL-3.0" (AGPL-3.0 plus sections 18–21). Section 18
  lets overlay/stream-bot tools like ChatToon integrate it without adopting the AGPL;
  section 19 forbids commercial, closed or hosted relay use. ChatToon does not ship it:
  it lives in the optional extras environment (``chattoon extras install tiktok``).

A source is a profile (``@user``): it waits while the profile is offline and picks up
the next live by itself. Likes, shares and joins are ignored (far too noisy to read);
a gift streak is read once, when it ends ("Rosa ×5"), never converted into money.
"""

from __future__ import annotations

import asyncio
import hashlib
import importlib
import logging
import re
import time
from types import SimpleNamespace

from .. import extras
from ..messages import ChatMessage
from .base import (Connector, ConnectorError, FatalError, NotLive, ProbeResult, RateLimited, TransientError,
                   Unsupported)

log = logging.getLogger(__name__)

CREDENTIAL = "tiktok/sign"  # {"api_key": "…"} for Euler Stream (optional)
INSTALL_HINT = "chattoon extras install tiktok"
RATE_LIMIT_WAIT = 300.0  # Euler Stream did not say how long: five minutes
CLOSE_TIMEOUT = 10.0

_ERRORS = ("TikTokLiveError", "UserOfflineError", "UserNotFoundError", "AgeRestrictedError",
           "SignatureRateLimitError", "SignAPIError", "WebcastBlockedError")
_PREFIX = re.compile(r"^TikTokLive v[\w.]+ ->\s*")

_import = importlib.import_module  # tests replace it to simulate a missing library


def load_library() -> SimpleNamespace:
    """TikTokLive as one namespace: the client, ``events`` and the error classes.

    Raises :class:`Unsupported` when the optional library is not installed."""
    extras.activate()
    try:
        package = _import("TikTokLive")
        events = _import("TikTokLive.events")
        errors = _import("TikTokLive.client.errors")
    except ImportError:
        raise Unsupported(f"TikTokLive is not installed. Install it with: {INSTALL_HINT}",
                          "missing-dependency") from None
    except Exception as e:  # noqa: BLE001 - a broken install must not take ChatToon down
        raise Unsupported(f"TikTokLive could not be loaded ({type(e).__name__}). Reinstall it with: "
                          f"{INSTALL_HINT}", "missing-dependency") from None
    return SimpleNamespace(TikTokLiveClient=package.TikTokLiveClient, events=events,
                           **{name: getattr(errors, name, None) for name in _ERRORS})


def _error_class(lib, name: str) -> type | tuple:
    cls = getattr(lib, name, None)
    return cls if isinstance(cls, type) else ()  # isinstance(x, ()) is always False


def _int(value) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _flag(obj, name: str) -> bool:
    try:
        return bool(getattr(obj, name, False))
    except Exception:  # noqa: BLE001 - library properties may fail on odd payloads
        return False


class TikTokConnector(Connector):
    platform = "tiktok"
    label = "TikTok"
    support = "experimental"
    reconnect_when_ended = True  # a profile: wait for the next live

    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)
        from .urls import detect

        self.user = detect(self.source.target, "tiktok").target  # "@user"; ValueError: bad target
        self._client = None
        self._ended: asyncio.Event | None = None
        self._secret = ""  # Euler Stream key, only kept to scrub it from error details

    # -- library and client --------------------------------------------------------

    def _library(self) -> SimpleNamespace:
        fake = self.ctx.extra.get("tiktok_module")
        return fake if fake is not None else load_library()

    async def _api_key(self) -> str:
        store = self.ctx.credentials
        if store is None:
            return ""
        try:
            value = await asyncio.to_thread(store.get, CREDENTIAL)
        except Exception as e:  # noqa: BLE001 - a locked keyring only means "no key"
            log.debug("tiktok source %s: no sign key (%s)", self.source.id, type(e).__name__)
            return ""
        key = str((value or {}).get("api_key") or "").strip()
        self._secret = key
        return key

    def _new_client(self, lib, api_key: str):
        # the key goes to this client's signer only (WebDefaults would leak it to every source)
        web_kwargs = {"signer_kwargs": {"sign_api_key": api_key}} if api_key else None
        client = lib.TikTokLiveClient(unique_id=self.user, web_kwargs=web_kwargs)
        if self.source.options.get("sign_tls", "verify") != "library":
            self._verify_tls(client)
        return client

    @staticmethod
    def _verify_tls(client) -> None:
        """TikTokLive 7.0.1 creates its Euler Stream client with ``verify_ssl=False``."""
        try:
            sdk = client.web.signer.sdk_client
            if getattr(sdk, "_async_client", True) is None and hasattr(sdk, "_verify_ssl"):
                sdk._verify_ssl = True  # read when the httpx client is created (first request)
        except Exception:  # noqa: BLE001 - another library version: leave it as it is
            log.debug("tiktok: could not enable TLS verification for the sign server")

    async def _shutdown(self, client) -> None:
        """Disconnect and close every HTTP client; never raises.

        Never ``client.close()`` nor cancelling ``connect()``: both end in
        ``loop.run_until_complete``, a RuntimeError inside a running loop."""
        steps = (("disconnect", lambda: client.disconnect()), ("web.close", lambda: client.web.close()),
                 ("signer", lambda: self._close_signer(client)))
        for name, step in steps:
            try:
                await asyncio.wait_for(step(), CLOSE_TIMEOUT)
            except Exception as e:  # noqa: BLE001 - closing is best effort
                log.debug("tiktok source %s: %s failed (%s)", self.source.id, name, type(e).__name__)

    @staticmethod
    async def _close_signer(client) -> None:
        signer = getattr(getattr(client, "web", None), "signer", None)
        inner = getattr(getattr(signer, "sdk_client", None), "_async_client", None)
        if inner is not None and hasattr(inner, "aclose"):
            await inner.aclose()

    async def close(self) -> None:
        client, self._client = self._client, None
        if client is not None:
            await self._shutdown(client)

    # -- errors ----------------------------------------------------------------------

    def _detail(self, error: BaseException) -> str:
        text = " ".join(_PREFIX.sub("", str(error)).split()) or type(error).__name__
        if self._secret:
            text = text.replace(self._secret, "***")
        return text[:300]

    @staticmethod
    def _rate_limit_wait(error) -> float:
        """Seconds Euler Stream asked to wait (``RateLimit-Reset`` first: TikTokLive's own
        ``retry_after`` reads ``RateLimit-Remaining``, which may be a request count)."""
        for name in ("reset_time", "retry_after"):
            try:
                number = float(getattr(error, name))
            except Exception:  # noqa: BLE001 - missing headers raise from cached properties
                continue
            seconds = number - time.time() if number > 1e9 else number
            if seconds > 0:
                return seconds
        return RATE_LIMIT_WAIT

    def _translate(self, lib, error: Exception) -> ConnectorError:
        detail = self._detail(error)
        if isinstance(error, ConnectorError):
            return error
        if isinstance(error, _error_class(lib, "UserOfflineError")):
            return NotLive(f"{self.user} is not live on TikTok right now.")
        if isinstance(error, _error_class(lib, "UserNotFoundError")):
            return FatalError(f"TikTok profile {self.user} not found (or it cannot go live).", "not-found")
        if isinstance(error, _error_class(lib, "AgeRestrictedError")):
            return FatalError(f"The live of {self.user} is age restricted; it cannot be read without a login.",
                              "age-restricted")
        if isinstance(error, _error_class(lib, "SignatureRateLimitError")):
            return RateLimited("Euler Stream (the TikTok signing service) rate limit reached. "
                               "An Euler Stream API key raises the limit.", self._rate_limit_wait(error))
        if isinstance(error, _error_class(lib, "SignAPIError")):
            return TransientError(f"Euler Stream sign server: {detail}", "sign-server")
        if isinstance(error, _error_class(lib, "WebcastBlockedError")):
            return TransientError(f"TikTok blocked the connection: {detail}", "blocked")
        return TransientError(f"{type(error).__name__}: {detail}")

    # -- session ---------------------------------------------------------------------

    async def session(self) -> None:
        lib = self._library()
        client = self._client = self._new_client(lib, await self._api_key())
        self._ended = asyncio.Event()
        try:
            try:
                if not await client.is_live():
                    raise NotLive(f"{self.user} is not live on TikTok right now.")
                self._listen(client, lib.events)
                task = await client.start(process_connect_events=not self.ctx.skip_backlog,
                                          fetch_live_check=False, fetch_gift_info=False)
                ended = asyncio.ensure_future(self._ended.wait())
                try:
                    await asyncio.wait({task, ended}, return_when=asyncio.FIRST_COMPLETED)
                finally:
                    ended.cancel()
                if task.done() and not task.cancelled() and task.exception() is not None:
                    raise task.exception()
            except ConnectorError:
                raise
            except Exception as e:  # noqa: BLE001 - httpx/websockets errors are not OSError
                raise self._translate(lib, e) from None
        finally:
            if self._client is client:
                self._client = None
            await self._shutdown(client)
        # LiveEndEvent / DisconnectEvent: the live is over; the supervisor waits for the next

    def _listen(self, client, events) -> None:
        handlers = (("ConnectEvent", self._on_connect), ("LiveEndEvent", self._on_end),
                    ("DisconnectEvent", self._on_end), ("CommentEvent", self._on_comment),
                    ("GiftEvent", self._on_gift), ("FollowEvent", self._on_follow),
                    ("SubNotifyEvent", self._on_subscribe))
        for name, handler in handlers:
            cls = getattr(events, name, None)
            if cls is not None:
                client.add_listener(cls, self._guard(handler))

    def _guard(self, handler):
        """Never let an exception reach the library's event emitter."""
        def run(event) -> None:
            try:
                handler(event)
            except Exception as e:  # noqa: BLE001
                log.debug("tiktok source %s: %s failed (%s)", self.source.id, handler.__name__, type(e).__name__)
        return run

    # -- events ------------------------------------------------------------------------

    def _on_connect(self, event) -> None:
        self.connected(self.user)

    def _on_end(self, event) -> None:
        if self._ended is not None:
            self._ended.set()

    def _base(self, event, kind: str, text: str = "") -> ChatMessage:
        user = getattr(event, "user", None)
        identity = getattr(event, "user_identity", None)
        common = getattr(event, "common", None)
        unique_id = str(getattr(user, "unique_id", "") or "")
        user_id = _int(getattr(user, "id", 0))
        created = _int(getattr(common, "create_time", 0))
        msg_id = _int(getattr(common, "msg_id", 0))
        if msg_id:
            mid = str(msg_id) if kind == "message" else f"{kind}:{msg_id}"
        else:  # stable fallback: the same event delivered twice keeps the same id
            raw = f"{kind}|{user_id or unique_id}|{created}|{text}"
            mid = f"{kind}:h{hashlib.sha1(raw.encode()).hexdigest()[:16]}"
        return ChatMessage(
            id=mid, author=str(getattr(user, "nickname", "") or unique_id or "?"),
            author_id=str(user_id) if user_id else unique_id, text=text,
            timestamp=(created / 1000 if created > 1e11 else created) or time.time(),
            is_moderator=_flag(identity, "is_moderator_of_anchor") or _flag(user, "is_moderator"),
            is_member=_flag(identity, "is_subscriber_of_anchor"), is_owner=_flag(identity, "is_anchor"),
            is_verified=_flag(user, "verified"), channel=self.user, event_type=kind,
        )

    def _on_comment(self, event) -> None:
        text = str(getattr(event, "content", "") or getattr(event, "comment", "") or "")
        if text.strip():
            self.emit(self._base(event, "message", text))

    def _on_gift(self, event) -> None:
        if _flag(event, "streaking"):
            return  # a streak is read once, by its final event (repeat_end)
        gift = getattr(event, "gift", None)
        name = str(getattr(gift, "name", "") or "Gift")
        count = max(1, _int(getattr(event, "repeat_count", 1)))
        msg = self._base(event, "gift")
        msg.superchat = f"{name} ×{count}" if count > 1 else name
        msg.paid_kind = "gift"
        self.emit(msg)

    def _on_follow(self, event) -> None:
        self.emit(self._base(event, "follow"))

    def _on_subscribe(self, event) -> None:
        self.emit(self._base(event, "subscription"))

    # -- test connection ---------------------------------------------------------------

    async def probe(self) -> ProbeResult:
        try:
            lib = self._library()
        except Unsupported as e:
            return ProbeResult(False, "unsupported", str(e))
        client = None
        try:
            client = self._new_client(lib, await self._api_key())
            live = await client.is_live()
        except Exception as e:  # noqa: BLE001 - every failure becomes a readable result
            error = self._translate(lib, e)
            if isinstance(error, NotLive):
                return ProbeResult(False, "offline", str(error), self.user)
            if isinstance(error, (FatalError, RateLimited)):
                return ProbeResult(False, error.code, str(error))
            return ProbeResult(False, "network", str(error))
        finally:
            if client is not None:
                await self._shutdown(client)
        if live:
            return ProbeResult(True, "live", channel=self.user)
        return ProbeResult(False, "offline", f"{self.user} is not live on TikTok right now.", self.user)
