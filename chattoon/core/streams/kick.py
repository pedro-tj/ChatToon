"""Kick chat: the public Pusher feed (unofficial, no login) or official webhooks.

Two ways to read a channel, chosen by the source option ``mode``:

* ``pusher`` — **EXPERIMENTAL and UNOFFICIAL.** This is how kick.com's own web page reads
  a public chat: the chatroom id comes from ``GET kick.com/api/v2/channels/<slug>`` and the
  messages from Kick's Pusher WebSocket (channel ``chatrooms.<id>.v2``). No login, works
  while the channel is offline, but Kick documents none of it and may change or block it
  at any time. ChatToon never tries to get past Cloudflare or any other challenge: when
  kick.com refuses the request, the source stops and asks the streamer to paste the
  chatroom id in the source options (option ``chatroom_id``), which skips that request.
* ``webhook`` — the OFFICIAL Kick API (support "limited"). It needs the streamer's own
  Kick app (Client ID in Settings › Accounts, Client Secret in the keyring under
  ``kick/app``) AND a public HTTPS URL that reaches this computer: Kick POSTs every event
  to the "Webhook URL" set in the Kick app settings ("Enable webhooks"), and the streamer
  forwards that URL (with their own tunnel or reverse proxy) to
  ``http://127.0.0.1:<port>/kick/webhook``. ChatToon only listens on 127.0.0.1; it never
  opens a public port nor starts a tunnel by itself. Every request is verified with
  Kick's RSA signature (public key fetched from the API, never hardcoded), recent
  timestamps only, no replays. Several webhook sources share one local receiver per port.
* ``auto`` (default) — the webhook when a Kick app is configured, otherwise Pusher.

Both turn badges into owner/moderator/subscriber/verified flags, replace emotes
(``[emote:123:name]``) with their name so the voice never reads the bracket syntax, map
subscriptions and Kicks into events, and honour moderation (deleted messages and bans).
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
import re
import time
from collections import OrderedDict
from collections.abc import Callable
from datetime import datetime, timezone

import aiohttp
from aiohttp import web

from ..messages import ChatMessage
from .base import (AuthRequired, Connector, ConnectorError, FatalError, ProbeResult, RateLimited, TransientError,
                   Unsupported, retry_after)

log = logging.getLogger(__name__)

KICK_BASE = "https://kick.com"
PUSHER_URL = "wss://ws-us2.pusher.com/app/32cbd69e4b950bf97679?protocol=7&client=js&version=8.4.0&flash=false"
ID_BASE = "https://id.kick.com"
API_BASE = "https://api.kick.com"
CREDENTIAL = "kick/app"  # {"client_secret": "..."}
WEBHOOK_PATH = "/kick/webhook"
WEBHOOK_EVENTS = ("chat.message.sent", "channel.subscription.new", "channel.subscription.gifts", "kicks.gifted",
                  "moderation.banned")

ACTIVITY_TIMEOUT = 120.0  # Pusher: ping after this long without data (the server may ask for less)
PONG_TIMEOUT = 30.0
MAX_BODY = 64 * 1024  # webhook bodies are small JSON documents
REPLAY_WINDOW = 300.0  # webhook timestamps older than this are replays
FUTURE_SKEW = 60.0  # …and newer than this are forged or a broken clock
KEY_REFRESH_MIN = 60.0  # refetch the public key at most once a minute (on a failed signature)

_EMOTE = re.compile(r"\[emote:\d+:([^\[\]]*)\]")
_EMOJI = re.compile(r"\[emoji:([^\[\]]*)\]")
_FRACTION = re.compile(r"\.(\d+)")

_OWNER_BADGES = {"broadcaster"}
_MOD_BADGES = {"moderator"}
_MEMBER_BADGES = {"subscriber", "founder", "og"}


def blocked_hint(slug: str) -> str:
    return (f"kick.com refused ChatToon's request (Cloudflare protection); ChatToon does not try to get past it. "
            f"Open https://kick.com/api/v2/channels/{slug} in your browser, copy the number in "
            f"\"chatroom\" › \"id\" and paste it in this source's \"Chatroom id\" option.")


# -- parsing helpers ---------------------------------------------------------------------

def clean_content(text: str) -> str:
    """Kick's inline emote syntax becomes the emote name; spaces are collapsed."""
    text = _EMOTE.sub(lambda m: f" {m.group(1)} ", text or "")
    text = _EMOJI.sub(lambda m: f" {m.group(1)} ", text)
    return " ".join(text.split())


def parse_time(value) -> float | None:
    """RFC 3339 / ISO 8601 (``Z``, offsets, any fraction length) -> epoch seconds."""
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if text[-1:] in ("Z", "z"):
        text = text[:-1] + "+00:00"
    text = _FRACTION.sub(lambda m: "." + (m.group(1) + "000000")[:6], text, count=1)
    try:
        when = datetime.fromisoformat(text)
    except ValueError:
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return when.timestamp()


def _data(value) -> dict:
    """Pusher frames carry ``data`` as a JSON *string* (sometimes as an object)."""
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            return {}
    return value if isinstance(value, dict) else {}


def _event_id(name: str, data: dict) -> str:
    """Pusher subscription events carry no id: derive a stable one from their content."""
    raw = json.dumps(data, sort_keys=True, default=str).encode()
    return f"{name}-{hashlib.sha1(raw).hexdigest()[:16]}"


def badge_flags(badges) -> dict[str, bool]:
    kinds = {str(b.get("type", "")).lower() for b in badges or [] if isinstance(b, dict)}
    return {"is_owner": bool(kinds & _OWNER_BADGES), "is_moderator": bool(kinds & _MOD_BADGES),
            "is_member": bool(kinds & _MEMBER_BADGES), "is_verified": "verified" in kinds}


def pusher_message(data: dict) -> ChatMessage:
    """``App\\Events\\ChatMessageEvent`` -> message."""
    sender = data.get("sender") or {}
    flags = badge_flags((sender.get("identity") or {}).get("badges"))
    return ChatMessage(
        id=str(data.get("id", "")), author=sender.get("username") or sender.get("slug") or "?",
        author_id=str(sender.get("id", "")), text=clean_content(data.get("content", "")),
        timestamp=parse_time(data.get("created_at")) or time.time(), **flags,
    )


def webhook_message(payload: dict) -> ChatMessage:
    """``chat.message.sent`` (official webhook) -> message."""
    sender = payload.get("sender") or {}
    flags = badge_flags((sender.get("identity") or {}).get("badges"))
    flags["is_verified"] = flags["is_verified"] or bool(sender.get("is_verified"))
    return ChatMessage(
        id=str(payload.get("message_id", "")), author=sender.get("username") or sender.get("channel_slug") or "?",
        author_id=str(sender.get("user_id", "")), text=clean_content(payload.get("content", "")),
        timestamp=parse_time(payload.get("created_at")) or time.time(), **flags,
    )


def _event(msg_id: str, user: dict, kind: str, label: str, text: str = "", paid_kind: str = "") -> ChatMessage:
    user = user if isinstance(user, dict) else {}
    anonymous = bool(user.get("is_anonymous"))
    return ChatMessage(
        id=msg_id, author="Anonymous" if anonymous else (user.get("username") or user.get("channel_slug") or "?"),
        author_id="" if anonymous else str(user.get("user_id", "") or user.get("id", "")),
        text=clean_content(text), event_type=kind, superchat=label[:80], paid_kind=paid_kind,
    )


def kicks_label(gift: dict) -> str:
    """``kicks.gifted`` -> "100 Kicks" (tolerant: the payload fields are young)."""
    amount = gift.get("amount", gift.get("kicks", gift.get("value")))
    try:
        number = int(float(amount))
    except (TypeError, ValueError):
        number = 0
    label = f"{number} Kicks" if number else "Kicks"
    name = gift.get("name")
    return f"{label} ({name})" if isinstance(name, str) and name else label


# -- webhook signature -----------------------------------------------------------------

def _crypto():
    """The optional ``cryptography`` primitives (Unsupported when the package is missing)."""
    try:
        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding, rsa
    except ImportError:
        raise Unsupported("Kick webhooks need the Python package 'cryptography' (python-cryptography).",
                          "missing-dependency") from None
    return InvalidSignature, hashes, serialization, padding, rsa


def load_public_key(pem: str):
    _, _, serialization, _, rsa = _crypto()
    key = serialization.load_pem_public_key(pem.encode())
    if not isinstance(key, rsa.RSAPublicKey):
        raise ValueError("Kick's public key is not an RSA key")
    return key


def verify_signature(public_key, message_id: str, timestamp: str, body: bytes, signature: str) -> bool:
    """RSA PKCS#1 v1.5 / SHA-256 over ``"<message id>.<timestamp>.<raw body>"``."""
    invalid, hashes, _, padding, _ = _crypto()
    try:
        raw = base64.b64decode(signature, validate=True)
        public_key.verify(raw, f"{message_id}.{timestamp}.".encode() + body, padding.PKCS1v15(), hashes.SHA256())
    except (invalid, ValueError):
        return False
    return True


# -- shared local webhook receiver --------------------------------------------------------

Handler = Callable[[str, str, dict], None]  # (event type, message id, payload)


class WebhookReceiver:
    """A tiny HTTP server on 127.0.0.1 that verifies Kick's requests and dispatches them
    by ``broadcaster.user_id`` to the source reading that channel."""

    def __init__(self, port: int, api_base: str, user_agent: str, clock: Callable[[], float] = time.time):
        self.port = port
        self.api_base = api_base.rstrip("/")
        self.user_agent = user_agent
        self.clock = clock
        self.loop = asyncio.get_running_loop()
        self.users = 0
        self.handlers: dict[str, tuple[object, Handler]] = {}
        self._runner: web.AppRunner | None = None
        self._http: aiohttp.ClientSession | None = None
        self._key = None
        self._key_at = 0.0
        self._seen: OrderedDict[str, None] = OrderedDict()
        self.started = asyncio.ensure_future(self._start())

    async def _start(self) -> None:
        app = web.Application(client_max_size=MAX_BODY)
        app.router.add_post(WEBHOOK_PATH, self.handle)
        runner = web.AppRunner(app, access_log=None)
        await runner.setup()
        try:
            await web.TCPSite(runner, "127.0.0.1", self.port).start()  # never 0.0.0.0
        except OSError:
            await runner.cleanup()
            raise FatalError(f"Port {self.port} is busy; choose another Kick webhook port in Settings › Accounts.",
                             "port-in-use") from None
        self._runner = runner
        self.port = runner.addresses[0][1]

    async def stop(self) -> None:
        if not self.started.done():
            self.started.cancel()
        if self._runner is not None:
            await self._runner.cleanup()
            self._runner = None
        if self._http is not None and not self._http.closed:
            await self._http.close()

    def register(self, broadcaster: str, owner: object, handler: Handler) -> None:
        current = self.handlers.get(broadcaster)
        if current is not None and current[0] is not owner:
            raise Unsupported("Another Kick source already receives this channel's webhooks.", "duplicate")
        self.handlers[broadcaster] = (owner, handler)

    def unregister(self, broadcaster: str, owner: object) -> None:
        if (self.handlers.get(broadcaster) or (None,))[0] is owner:
            del self.handlers[broadcaster]

    async def public_key(self, refresh: bool = False):
        if self._key is not None and not refresh:
            return self._key
        if self._key is not None and time.monotonic() - self._key_at < KEY_REFRESH_MIN:
            return self._key  # a forged request must not make us hammer Kick's API
        if self._http is None or self._http.closed:
            self._http = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15),
                                               headers={"User-Agent": self.user_agent})
        async with self._http.get(f"{self.api_base}/public/v1/public-key") as resp:
            if resp.status != 200:
                raise TransientError(f"Kick public key: HTTP {resp.status}")
            data = await resp.json(content_type=None)
        self._key = load_public_key(str((data.get("data") or {}).get("public_key", "")))
        self._key_at = time.monotonic()
        return self._key

    async def _verified(self, message_id: str, timestamp: str, body: bytes, signature: str) -> bool:
        key = await self.public_key()
        if verify_signature(key, message_id, timestamp, body, signature):
            return True
        fresh = await self.public_key(refresh=True)  # Kick may have rotated its key
        return fresh is not key and verify_signature(fresh, message_id, timestamp, body, signature)

    async def handle(self, request: web.Request) -> web.Response:
        if request.content_length is not None and request.content_length > MAX_BODY:
            return web.Response(status=413)
        try:
            body = await request.read()
        except web.HTTPRequestEntityTooLarge:
            return web.Response(status=413)
        headers = request.headers
        message_id = headers.get("Kick-Event-Message-Id", "")
        timestamp = headers.get("Kick-Event-Message-Timestamp", "")
        signature = headers.get("Kick-Event-Signature", "")
        kind = headers.get("Kick-Event-Type", "")
        if not (message_id and timestamp and signature and kind) or len(message_id) > 200 or len(timestamp) > 64:
            return web.Response(status=400, text="missing Kick-Event headers")
        when = parse_time(timestamp)
        now = self.clock()
        if when is None or now - when > REPLAY_WINDOW or when - now > FUTURE_SKEW:
            return web.Response(status=400, text="stale or invalid timestamp")
        try:
            ok = await self._verified(message_id, timestamp, body, signature)
        except (ConnectorError, aiohttp.ClientError, OSError, asyncio.TimeoutError, ValueError):
            log.warning("Kick webhook: the public key could not be fetched")
            return web.Response(status=503)  # Kick retries later
        if not ok:
            return web.Response(status=401, text="bad signature")
        if message_id in self._seen:
            return web.Response(status=200, text="duplicate")
        self._seen[message_id] = None
        if len(self._seen) > 5000:
            self._seen.popitem(last=False)
        try:
            payload = json.loads(body)
        except ValueError:
            return web.Response(status=400, text="invalid JSON")
        if not isinstance(payload, dict):
            return web.Response(status=400, text="invalid JSON")
        broadcaster = str((payload.get("broadcaster") or {}).get("user_id", ""))
        target = self.handlers.get(broadcaster)
        if target is not None:
            try:
                target[1](kind, message_id, payload)
            except (KeyError, TypeError, ValueError, AttributeError):
                log.warning("Kick webhook: odd %s payload ignored", kind)
        return web.Response(status=200, text="ok")


_RECEIVERS: dict[int, WebhookReceiver] = {}


async def acquire_receiver(port: int, api_base: str, user_agent: str) -> WebhookReceiver:
    """The receiver listening on ``port`` (started on first use, reference counted)."""
    receiver = _RECEIVERS.get(port)
    if receiver is None or receiver.loop is not asyncio.get_running_loop() or receiver.started.cancelled():
        receiver = _RECEIVERS[port] = WebhookReceiver(port, api_base, user_agent)
    receiver.users += 1
    try:
        await asyncio.shield(receiver.started)
    except BaseException:
        await release_receiver(receiver)
        raise
    return receiver


async def release_receiver(receiver: WebhookReceiver) -> None:
    receiver.users -= 1
    if receiver.users > 0:
        return
    for port, current in list(_RECEIVERS.items()):
        if current is receiver:
            del _RECEIVERS[port]
    await receiver.stop()


# -- connector --------------------------------------------------------------------------

class KickConnector(Connector):
    platform = "kick"
    label = "Kick"
    support = "experimental"  # the default path (Pusher) is unofficial
    reconnect_when_ended = True

    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)
        from .urls import detect

        self.slug = detect(self.source.target, "kick").target  # ValueError: bad channel
        extra = self.ctx.extra
        self.kick_base = extra.get("kick_base", KICK_BASE).rstrip("/")
        self.pusher_url = extra.get("kick_pusher_url", PUSHER_URL)
        self.id_base = extra.get("kick_id_base", ID_BASE).rstrip("/")
        self.api_base = extra.get("kick_api_base", API_BASE).rstrip("/")
        self.activity_override = extra.get("kick_activity_timeout")
        self.pong_timeout = float(extra.get("kick_pong_timeout", PONG_TIMEOUT))
        self._session: aiohttp.ClientSession | None = None
        self.mode_used = ""
        self.display = self.slug
        self._chatroom_id = ""
        self._token = ""
        self._token_expires = 0.0
        self._subscriptions: list[str] = []
        self.webhook_port = 0

    async def _http(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30),
                                                  headers={"User-Agent": self.ctx.user_agent})
        return self._session

    async def close(self) -> None:
        if self._subscriptions:
            try:
                await asyncio.wait_for(self._unsubscribe(), 10)
            except (ConnectorError, aiohttp.ClientError, OSError, asyncio.TimeoutError, ValueError):
                log.info("Kick: could not delete the webhook subscriptions (they expire on Kick's side)")
        if self._session is not None and not self._session.closed:
            await self._session.close()

    async def _app(self) -> tuple[str, str]:
        """(client id, client secret) of the streamer's Kick app, or Unsupported."""
        client = str(getattr(self.ctx.apps, "kick_client_id", "") or "").strip()
        store = self.ctx.credentials
        stored = await asyncio.to_thread(store.get, CREDENTIAL) if store is not None else None
        secret = str((stored or {}).get("client_secret", "") or "").strip()
        if not client or not secret:
            raise Unsupported("Webhook mode needs your Kick app: set its Client ID and Client Secret in "
                              "Settings › Accounts.", "no-app")
        return client, secret

    async def _mode(self) -> str:
        mode = self.source.options.get("mode", "auto")
        if mode in ("pusher", "webhook"):
            return mode
        try:
            await self._app()
        except Unsupported:
            return "pusher"
        return "webhook"

    async def session(self) -> None:
        self.mode_used = await self._mode()
        if self.mode_used == "webhook":
            await self._webhook()
        else:
            await self._pusher()

    # -- Pusher (unofficial) ------------------------------------------------------------

    async def _channel_info(self) -> dict:
        """kick.com's own channel endpoint (chatroom id, live state, display name)."""
        http = await self._http()
        async with http.get(f"{self.kick_base}/api/v2/channels/{self.slug}",
                            headers={"Accept": "application/json"}) as resp:
            if resp.status == 404:
                raise FatalError(f"Kick channel '{self.slug}' not found.", "not-found")
            if resp.status == 429:
                raise RateLimited("kick.com rate limit", retry_after(resp.headers, 60))
            is_json = "json" in (resp.content_type or "")
            if resp.status == 403 or (resp.status in (200, 503) and not is_json):
                raise FatalError(blocked_hint(self.slug), "blocked")
            if resp.status != 200:
                raise TransientError(f"kick.com channel: HTTP {resp.status}")
            info = await resp.json(content_type=None)
        if not isinstance(info, dict):
            raise FatalError(blocked_hint(self.slug), "blocked")
        chatroom = (info.get("chatroom") or {}).get("id")
        if chatroom is None or not str(chatroom).isdigit():
            raise FatalError("kick.com did not say which chatroom this channel uses. " + blocked_hint(self.slug),
                             "no-chatroom")
        self._chatroom_id = str(chatroom)
        self.display = (info.get("user") or {}).get("username") or self.slug
        return info

    def _manual_chatroom(self) -> str:
        manual = self.source.options.get("chatroom_id", "").strip()
        if manual and not manual.isdigit():
            raise FatalError("The Kick chatroom id must contain only digits.", "invalid")
        return manual

    async def _chatroom(self) -> str:
        if not self._chatroom_id:
            self._chatroom_id = self._manual_chatroom()
        if not self._chatroom_id:
            await self._channel_info()
        return self._chatroom_id

    async def _pusher(self) -> None:
        chatroom = await self._chatroom()
        http = await self._http()
        try:
            ws = await http.ws_connect(self.pusher_url, heartbeat=None, max_msg_size=1 << 20)
        except aiohttp.WSServerHandshakeError as e:
            if e.status == 403:
                raise FatalError("Kick's chat server refused the connection (HTTP 403).", "blocked") from None
            raise TransientError(f"Kick chat handshake: HTTP {e.status}") from None
        try:
            activity = await self._established(ws)
            await ws.send_json({"event": "pusher:subscribe",
                                "data": {"auth": "", "channel": f"chatrooms.{chatroom}.v2"}})
            await self._pusher_loop(ws, activity)
        finally:
            await ws.close()

    async def _established(self, ws) -> float:
        try:
            msg = await ws.receive(timeout=15)
        except asyncio.TimeoutError:
            raise TransientError("Kick chat: no greeting from the server") from None
        if msg.type != aiohttp.WSMsgType.TEXT:
            raise self._closed(ws.close_code)
        frame = json.loads(msg.data)
        if frame.get("event") == "pusher:error":
            raise self._pusher_error(_data(frame.get("data")))
        if frame.get("event") != "pusher:connection_established":
            raise TransientError("Kick chat: unexpected greeting")
        if self.activity_override is not None:
            return float(self.activity_override)
        try:
            server = float(_data(frame.get("data")).get("activity_timeout") or ACTIVITY_TIMEOUT)
        except (TypeError, ValueError):
            server = ACTIVITY_TIMEOUT
        return max(1.0, min(ACTIVITY_TIMEOUT, server))

    async def _pusher_loop(self, ws, activity: float) -> None:
        waiting_pong = False
        while True:
            try:
                msg = await ws.receive(timeout=self.pong_timeout if waiting_pong else activity)
            except asyncio.TimeoutError:
                if waiting_pong:
                    raise TransientError("Kick chat did not answer the keepalive") from None
                await ws.send_json({"event": "pusher:ping", "data": {}})
                waiting_pong = True
                continue
            if msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.CLOSING, aiohttp.WSMsgType.ERROR,
                            aiohttp.WSMsgType.CLOSE):
                raise self._closed(ws.close_code)
            if msg.type != aiohttp.WSMsgType.TEXT:
                continue
            waiting_pong = False  # any data proves the connection is alive
            try:
                frame = json.loads(msg.data)
            except ValueError:
                continue
            if not isinstance(frame, dict):
                continue
            event = frame.get("event", "")
            if event == "pusher:ping":
                await ws.send_json({"event": "pusher:pong", "data": {}})
            elif event == "pusher:error":
                raise self._pusher_error(_data(frame.get("data")))
            elif event == "pusher_internal:subscription_succeeded":
                self.connected(self.display)  # the chat works offline too: connected regardless
            elif event.startswith("App\\Events\\"):
                self._pusher_event(event[len("App\\Events\\"):], _data(frame.get("data")))

    def _pusher_event(self, name: str, data: dict) -> None:
        if name == "ChatMessageEvent":
            msg = pusher_message(data)
            msg.channel = self.display
            self.emit(msg)
        elif name == "MessageDeletedEvent":
            message_id = (data.get("message") or {}).get("id")
            if message_id:
                self.retract(message_id=str(message_id))
        elif name == "UserBannedEvent":
            user_id = (data.get("user") or {}).get("id")
            if user_id:
                self.retract(author_id=str(user_id))
        elif name == "SubscriptionEvent":
            months = data.get("months")
            label = f"Sub ({months} months)" if isinstance(months, int) and months > 1 else "Sub"
            user = {"username": data.get("username", "")}
            self.emit(_event(_event_id(name, data), user, "subscription", label, paid_kind="subscription"))
        elif name == "GiftedSubscriptionsEvent":
            gifted = data.get("gifted_usernames") or []
            count = len(gifted) if isinstance(gifted, list) else 0
            label = f"{count} gifted subs" if count != 1 else "1 gifted sub"
            user = {"username": data.get("gifter_username", "")}
            self.emit(_event(_event_id(name, data), user, "subscription", label, paid_kind="subscription"))
        # StreamerIsLive / StopStreamBroadcast and anything else: the chat keeps working, ignore

    @staticmethod
    def _pusher_error(data: dict) -> ConnectorError:
        try:
            code = int(data.get("code") or 0)
        except (TypeError, ValueError):
            code = 0
        text = str(data.get("message") or "")[:120]
        if 4000 <= code < 4100:
            return FatalError(f"Kick's chat server refused the connection ({code} {text}).", "pusher-refused")
        if 4100 <= code < 4200:
            return TransientError(f"Kick's chat server is busy ({code} {text}); trying again later.")
        return TransientError(f"Kick chat error {code} {text}".strip())

    def _closed(self, code: int | None) -> ConnectorError:
        code = code or 0
        if 4000 <= code < 4100:
            return FatalError(f"Kick's chat server closed the connection for good ({code}).", "pusher-refused")
        return TransientError(f"Kick chat connection closed ({code})")

    # -- official API + webhooks ---------------------------------------------------------

    async def _app_token(self, force: bool = False) -> str:
        if self._token and not force and time.time() < self._token_expires - 60:
            return self._token
        client, secret = await self._app()
        http = await self._http()
        async with http.post(f"{self.id_base}/oauth/token", data={
                "grant_type": "client_credentials", "client_id": client, "client_secret": secret}) as resp:
            if resp.status in (400, 401, 403):
                raise AuthRequired("Kick refused your app's Client ID / Client Secret. Check them in "
                                   "Settings › Accounts.")
            if resp.status == 429:
                raise RateLimited("Kick rate limit", retry_after(resp.headers, 60))
            if resp.status != 200:
                raise TransientError(f"Kick token: HTTP {resp.status}")
            data = await resp.json(content_type=None)
        token = data.get("access_token") if isinstance(data, dict) else None
        if not token:
            raise TransientError("Kick token: no access token in the answer")
        self._token = str(token)
        self._token_expires = time.time() + float(data.get("expires_in") or 3600)
        return self._token

    async def _api(self, method: str, path: str, **kw) -> tuple[int, dict]:
        status, data = await self._api_once(method, path, False, **kw)
        if status == 401:  # the app token expired early: get a new one once
            status, data = await self._api_once(method, path, True, **kw)
        return status, data

    async def _api_once(self, method: str, path: str, fresh: bool, **kw) -> tuple[int, dict]:
        http = await self._http()
        token = await self._app_token(force=fresh)
        async with http.request(method, f"{self.api_base}{path}", headers={"Authorization": f"Bearer {token}"},
                                **kw) as resp:
            if resp.status == 429:
                raise RateLimited("Kick rate limit", retry_after(resp.headers, 30))
            try:
                data = await resp.json(content_type=None)
            except ValueError:
                data = {}
            return resp.status, data if isinstance(data, dict) else {}

    async def _kick_channel(self) -> tuple[str, bool]:
        """(broadcaster user id, is live) from the official API."""
        status, data = await self._api("GET", "/public/v1/channels", params={"slug": self.slug})
        if status == 401:
            raise AuthRequired("Kick refused your app's token. Check the app in Settings › Accounts.")
        if status == 404:
            raise FatalError(f"Kick channel '{self.slug}' not found.", "not-found")
        if status != 200:
            raise TransientError(f"Kick channels: HTTP {status}")
        rows = data.get("data") or []
        if not rows or not rows[0].get("broadcaster_user_id"):
            raise FatalError(f"Kick channel '{self.slug}' not found.", "not-found")
        row = rows[0]
        return str(row["broadcaster_user_id"]), bool((row.get("stream") or {}).get("is_live"))

    async def _subscribe(self, broadcaster: str) -> None:
        body = {"broadcaster_user_id": int(broadcaster), "method": "webhook",
                "events": [{"name": name, "version": 1} for name in WEBHOOK_EVENTS]}
        status, data = await self._api("POST", "/public/v1/events/subscriptions", json=body)
        if status == 401:
            raise AuthRequired("Kick refused your app's token. Check the app in Settings › Accounts.")
        if status >= 500:
            raise TransientError(f"Kick subscriptions: HTTP {status}")
        if status not in (200, 201):
            detail = " ".join(f"HTTP {status} {data.get('message') or ''}".split())[:140]
            raise FatalError(f"Kick refused the webhook subscription ({detail}). Check that webhooks are enabled "
                             "in your Kick app.", "subscribe-failed")
        failed = []
        for item in data.get("data") or []:
            sub_id = item.get("subscription_id") or item.get("id")
            if sub_id:
                self._subscriptions.append(str(sub_id))
            elif item.get("error"):
                failed.append(str(item.get("name", "")))
        if "chat.message.sent" in failed:
            raise FatalError("Kick refused the chat webhook subscription.", "subscribe-failed")

    async def _unsubscribe(self) -> None:
        ids, self._subscriptions = self._subscriptions, []
        if ids:
            await self._api("DELETE", "/public/v1/events/subscriptions", params=[("id", i) for i in ids])

    async def _webhook(self) -> None:
        _crypto()
        await self._app()
        broadcaster, _live = await self._kick_channel()
        if self._subscriptions:  # left over by a previous attempt
            await self._unsubscribe()
        port = int(getattr(self.ctx.apps, "kick_webhook_port", 8790))
        receiver = await acquire_receiver(port, self.api_base, self.ctx.user_agent)
        try:
            receiver.register(broadcaster, self, self._on_webhook)
            try:
                self.webhook_port = receiver.port
                await self._subscribe(broadcaster)
                self.status.channel = self.slug
                self.set_status("connected", "webhook", (
                    "Kick sends the chat to the public HTTPS Webhook URL set in your Kick app (Enable webhooks). "
                    f"Forward that URL to http://127.0.0.1:{receiver.port}{WEBHOOK_PATH} on this computer; "
                    "ChatToon never opens a public port by itself."))
                await asyncio.Event().wait()  # events arrive through the receiver
            finally:
                receiver.unregister(broadcaster, self)
        finally:
            await release_receiver(receiver)

    def _on_webhook(self, kind: str, message_id: str, payload: dict) -> None:
        if kind == "chat.message.sent":
            msg = webhook_message(payload)
            msg.channel = self.slug
            self.emit(msg)
        elif kind in ("channel.subscription.new", "channel.subscription.renewal"):
            months = payload.get("duration")
            label = f"Sub ({months} months)" if isinstance(months, int) and months > 1 else "Sub"
            self.emit(_event(message_id, payload.get("subscriber"), "subscription", label, paid_kind="subscription"))
        elif kind == "channel.subscription.gifts":
            giftees = payload.get("giftees") or []
            count = len(giftees) if isinstance(giftees, list) else 0
            label = f"{count} gifted subs" if count != 1 else "1 gifted sub"
            self.emit(_event(message_id, payload.get("gifter"), "subscription", label, paid_kind="subscription"))
        elif kind == "kicks.gifted":
            gift = payload.get("gift") or {}
            self.emit(_event(message_id, payload.get("sender"), "gift", kicks_label(gift),
                             text=str(gift.get("message") or ""), paid_kind="kicks"))
        elif kind == "moderation.banned":
            user_id = (payload.get("banned_user") or {}).get("user_id")
            if user_id:
                self.retract(author_id=str(user_id))

    # -- test connection ----------------------------------------------------------------

    async def probe(self) -> ProbeResult:
        try:
            if await self._mode() == "webhook":
                _crypto()
                _, live = await self._kick_channel()
                return ProbeResult(True, "live" if live else "offline", channel=self.slug)
            return await self._probe_pusher()
        except (AuthRequired, Unsupported, FatalError, RateLimited) as e:
            return ProbeResult(False, e.code, str(e))
        except (aiohttp.ClientError, OSError, asyncio.TimeoutError, TransientError) as e:
            return ProbeResult(False, "network", type(e).__name__)

    async def _probe_pusher(self) -> ProbeResult:
        manual = self._manual_chatroom()
        try:
            info = await self._channel_info()
        except FatalError as e:
            if manual and e.code in ("blocked", "no-chatroom"):
                return ProbeResult(True, "ready", "Using the chatroom id typed in the source options.", self.slug)
            raise
        if manual:
            self._chatroom_id = manual
        return ProbeResult(True, "live" if info.get("livestream") else "offline", channel=self.display)

