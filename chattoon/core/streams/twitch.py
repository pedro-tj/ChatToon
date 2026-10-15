"""Twitch chat: official EventSub WebSocket (with a login) or anonymous read-only IRC.

Two ways to read a channel, chosen by the source option ``mode``:

* ``account`` — the official, recommended way. The streamer connects a Twitch account
  once with the Device Code flow (no password, no client secret; a *Public* app's Client
  ID is enough) granting only ``user:read:chat``. ChatToon then subscribes to
  ``channel.chat.message``, ``channel.chat.notification`` and the moderation events over
  ``wss://eventsub.wss.twitch.tv/ws``. Tokens are validated at start and every hour (a
  Twitch requirement) and refreshed automatically; refresh tokens are single-use, so the
  new one is stored every time.
* ``anonymous`` — no login at all: Twitch's IRC chat server read as a ``justinfan``
  guest. Long-standing and still "Active" in Twitch's lifecycle page, but the anonymous
  login itself is not documented, so the interface labels it as such.
* ``auto`` (default) — the account when one is connected, otherwise anonymous.

Both turn badges into moderator/subscriber/owner flags, Bits into paid messages and
subscriptions/raids into events, and both honour moderation: a message deleted or a
viewer timed out by the channel's moderators is never read by the avatar.
"""

from __future__ import annotations

import asyncio
import random
import time

import aiohttp

from ..messages import ChatMessage
from .base import (AuthRequired, Connector, FatalError, ProbeResult, RateLimited, StreamMetadata, TransientError,
                   Unsupported, retry_after)

ID_BASE = "https://id.twitch.tv"
API_BASE = "https://api.twitch.tv"
EVENTSUB_URL = "wss://eventsub.wss.twitch.tv/ws"
IRC_URL = "wss://irc-ws.chat.twitch.tv:443"
SCOPES = "user:read:chat"
CREDENTIAL = "twitch/account"
# Client ID of a "Public" Twitch application registered for ChatToon. Public client ids
# are not secrets; leave empty to let each streamer use their own (Settings › Accounts).
DEFAULT_CLIENT_ID = ""

_SUBSCRIPTIONS = ("channel.chat.message", "channel.chat.notification", "channel.chat.message_delete",
                  "channel.chat.clear_user_messages")


def client_id(apps) -> str:
    return (getattr(apps, "twitch_client_id", "") or DEFAULT_CLIENT_ID).strip()


# -- account (Device Code Grant) -------------------------------------------------

class TwitchAuth:
    """Device Code login, validation, refresh and revocation for a Public client."""

    def __init__(self, store, client: str, id_base: str = ID_BASE):
        self.store, self.client_id, self.id_base = store, client, id_base.rstrip("/")

    def account(self) -> dict | None:
        return self.store.get(CREDENTIAL) if self.store is not None else None

    async def start(self, session: aiohttp.ClientSession) -> dict:
        """Ask for a device code; the streamer types ``user_code`` at ``verification_uri``."""
        if not self.client_id:
            raise Unsupported("Set the Twitch Client ID first (Settings › Accounts).", "no-client-id")
        async with session.post(f"{self.id_base}/oauth2/device",
                                data={"client_id": self.client_id, "scopes": SCOPES}) as resp:
            data = await resp.json(content_type=None)
            if resp.status != 200:
                raise FatalError(str(data.get("message") or f"HTTP {resp.status}"), "auth-failed")
        return data

    async def finish(self, session: aiohttp.ClientSession, device: dict, timeout: float = 600) -> dict:
        """Poll until the streamer approves (or the code expires); stores the account."""
        interval = max(1.0, float(device.get("interval", 5)))
        deadline = time.monotonic() + min(timeout, float(device.get("expires_in", 1800)))
        body = {"client_id": self.client_id, "scopes": SCOPES, "device_code": device["device_code"],
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code"}
        while time.monotonic() < deadline:
            await asyncio.sleep(interval)
            async with session.post(f"{self.id_base}/oauth2/token", data=body) as resp:
                data = await resp.json(content_type=None)
            if resp.status == 200 and data.get("access_token"):
                return await self._save(session, data)
            message = str(data.get("message", ""))
            if "slow_down" in message:
                interval += 5
            elif "pending" not in message:
                raise AuthRequired(message or "The login was not approved.", "auth-denied")
        raise AuthRequired("The login code expired. Try again.", "auth-expired")

    async def _save(self, session: aiohttp.ClientSession, token: dict) -> dict:
        info = await self.validate(session, token["access_token"])
        if info is None:
            raise AuthRequired("Twitch did not accept the new token.")
        account = {
            "access_token": token["access_token"], "refresh_token": token.get("refresh_token", ""),
            "expires_at": time.time() + float(token.get("expires_in", 3600)), "login": info.get("login", ""),
            "user_id": info.get("user_id", ""), "client_id": self.client_id, "validated_at": time.time(),
        }
        await asyncio.to_thread(self.store.set, CREDENTIAL, account)
        return account

    async def validate(self, session: aiohttp.ClientSession, access_token: str) -> dict | None:
        async with session.get(f"{self.id_base}/oauth2/validate",
                               headers={"Authorization": f"OAuth {access_token}"}) as resp:
            if resp.status == 401:
                return None
            if resp.status != 200:
                raise TransientError(f"token validation: HTTP {resp.status}")
            return await resp.json(content_type=None)

    async def refresh(self, session: aiohttp.ClientSession, account: dict) -> dict:
        if not account.get("refresh_token"):
            raise AuthRequired("The Twitch login expired. Connect the account again.")
        async with session.post(f"{self.id_base}/oauth2/token", data={
                "grant_type": "refresh_token", "refresh_token": account["refresh_token"],
                "client_id": account.get("client_id") or self.client_id}) as resp:
            data = await resp.json(content_type=None)
            if resp.status in (400, 401):
                raise AuthRequired("The Twitch login expired. Connect the account again.")
            if resp.status != 200:
                raise TransientError(f"token refresh: HTTP {resp.status}")
        return await self._save(session, data)  # refresh tokens are single-use: keep the new one

    async def ensure(self, session: aiohttp.ClientSession, force: bool = False) -> dict:
        """A valid account: validated at least hourly, refreshed when needed."""
        account = await asyncio.to_thread(self.account)
        if not account:
            raise AuthRequired("Connect a Twitch account first.")
        stale = time.time() - float(account.get("validated_at", 0)) > 3000
        if force or stale or time.time() > float(account.get("expires_at", 0)) - 120:
            info = await self.validate(session, account["access_token"])
            if info is None or float(info.get("expires_in", 0)) < 120:
                return await self.refresh(session, account)
            account["validated_at"] = time.time()
            account["expires_at"] = time.time() + float(info.get("expires_in", 0))
            await asyncio.to_thread(self.store.set, CREDENTIAL, account)
        return account

    async def revoke(self, session: aiohttp.ClientSession) -> None:
        """Log out: revoke at Twitch (best effort) and erase the local copy."""
        account = await asyncio.to_thread(self.account)
        if account:
            try:
                async with session.post(f"{self.id_base}/oauth2/revoke", data={
                        "client_id": account.get("client_id") or self.client_id,
                        "token": account["access_token"]}):
                    pass
            except (aiohttp.ClientError, OSError, asyncio.TimeoutError):
                pass
        await asyncio.to_thread(self.store.delete, CREDENTIAL)


# -- IRC helpers ---------------------------------------------------------------------

_UNESCAPE = {"s": " ", ":": ";", "\\": "\\", "r": "\r", "n": "\n"}


def _tag_value(value: str) -> str:
    out, i = [], 0
    while i < len(value):
        c = value[i]
        if c == "\\" and i + 1 < len(value):
            out.append(_UNESCAPE.get(value[i + 1], value[i + 1]))
            i += 2
            continue
        out.append(c)
        i += 1
    return "".join(out)


def parse_irc(line: str) -> tuple[dict[str, str], str, str, list[str], str]:
    """``@tags :prefix COMMAND params :trailing`` -> (tags, prefix, command, params, trailing)."""
    tags: dict[str, str] = {}
    if line.startswith("@"):
        raw, _, line = line[1:].partition(" ")
        for item in raw.split(";"):
            key, _, value = item.partition("=")
            tags[key] = _tag_value(value)
    prefix = ""
    if line.startswith(":"):
        prefix, _, line = line[1:].partition(" ")
    line, _, trailing = line.partition(" :")
    parts = line.split()
    return tags, prefix, (parts[0] if parts else ""), parts[1:], trailing


def _badges(value: str) -> set[str]:
    return {b.split("/")[0] for b in value.split(",") if b}


def irc_message(tags: dict[str, str], prefix: str, text: str) -> ChatMessage:
    badges = _badges(tags.get("badges", ""))
    login = prefix.split("!")[0]
    if text.startswith("\x01ACTION ") and text.endswith("\x01"):
        text = text[8:-1]  # "/me" messages
    bits = int(tags.get("bits") or 0) if (tags.get("bits") or "0").isdigit() else 0
    try:
        ts = int(tags.get("tmi-sent-ts", "0")) / 1000 or time.time()
    except ValueError:
        ts = time.time()
    return ChatMessage(
        id=tags.get("id", ""), author=tags.get("display-name") or login or "?", author_id=tags.get("user-id", ""),
        text=text, timestamp=ts, is_moderator=tags.get("mod") == "1" or "moderator" in badges,
        is_owner="broadcaster" in badges, is_member=tags.get("subscriber") == "1" or bool({"subscriber", "founder"} & badges),
        is_verified="partner" in badges, superchat=f"{bits} bits" if bits else "", paid_kind="bits" if bits else "",
        event_type="paid" if bits else "message",
    )


_USERNOTICE_EVENTS = {"sub": "subscription", "resub": "subscription", "subgift": "subscription",
                      "submysterygift": "subscription", "giftpaidupgrade": "subscription",
                      "anongiftpaidupgrade": "subscription", "primepaidupgrade": "subscription", "raid": "raid"}


# -- EventSub helpers --------------------------------------------------------------------

def eventsub_message(event: dict) -> ChatMessage:
    badges = {b.get("set_id", "") for b in event.get("badges") or []}
    bits = int(((event.get("cheer") or {}).get("bits")) or 0)
    return ChatMessage(
        id=event.get("message_id", ""), author=event.get("chatter_user_name") or event.get("chatter_user_login") or "?",
        author_id=str(event.get("chatter_user_id", "")), text=(event.get("message") or {}).get("text", ""),
        is_moderator="moderator" in badges, is_owner="broadcaster" in badges,
        is_member=bool({"subscriber", "founder"} & badges), is_verified="partner" in badges,
        superchat=f"{bits} bits" if bits else "", paid_kind="bits" if bits else "",
        event_type="paid" if bits else "message",
    )


_NOTICE_EVENTS = {"sub": "subscription", "resub": "subscription", "sub_gift": "subscription",
                  "community_sub_gift": "subscription", "gift_paid_upgrade": "subscription",
                  "prime_paid_upgrade": "subscription", "raid": "raid"}


# -- connector --------------------------------------------------------------------------

class TwitchConnector(Connector):
    platform = "twitch"
    label = "Twitch"
    support = "functional"

    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)
        from .urls import detect

        self.login = detect(self.source.target, "twitch").target  # ValueError: bad channel
        extra = self.ctx.extra
        self.id_base = extra.get("twitch_id_base", ID_BASE)
        self.api_base = extra.get("twitch_api_base", API_BASE).rstrip("/")
        self.eventsub_url = extra.get("twitch_eventsub_url", EVENTSUB_URL)
        self.irc_url = extra.get("twitch_irc_url", IRC_URL)
        self._session: aiohttp.ClientSession | None = None
        self.mode_used = ""

    def auth(self) -> TwitchAuth:
        return TwitchAuth(self.ctx.credentials, client_id(self.ctx.apps), self.id_base)

    async def _http(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30),
                                                  headers={"User-Agent": self.ctx.user_agent})
        return self._session

    async def close(self) -> None:
        if self._session is not None and not self._session.closed:
            await self._session.close()

    async def _use_account(self) -> bool:
        mode = self.source.options.get("mode", "auto")
        if mode == "anonymous":
            return False
        has = bool(await asyncio.to_thread(self.auth().account)) if self.ctx.credentials is not None else False
        if mode == "account":
            if not client_id(self.ctx.apps):
                raise Unsupported("Set the Twitch Client ID first (Settings › Accounts).", "no-client-id")
            if not has:
                raise AuthRequired("Connect a Twitch account first.")
            return True
        return has and bool(client_id(self.ctx.apps))

    async def session(self) -> None:
        if await self._use_account():
            self.mode_used = "account"
            await self._eventsub()
        else:
            self.mode_used = "anonymous"
            await self._irc()

    # -- anonymous IRC ------------------------------------------------------------

    async def _irc(self) -> None:
        http = await self._http()
        async with http.ws_connect(self.irc_url, heartbeat=None, max_msg_size=1 << 20) as ws:
            await ws.send_str("CAP REQ :twitch.tv/tags twitch.tv/commands")
            await ws.send_str(f"NICK justinfan{random.randint(10000, 99999)}")
            await ws.send_str(f"JOIN #{self.login}")
            joined = False
            while True:
                try:
                    msg = await ws.receive(timeout=360)  # Twitch PINGs about every 5 minutes
                except asyncio.TimeoutError:
                    raise TransientError("no data from Twitch for 6 minutes") from None
                if msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.CLOSING, aiohttp.WSMsgType.ERROR):
                    raise TransientError("Twitch closed the chat connection")
                if msg.type != aiohttp.WSMsgType.TEXT:
                    continue
                for line in msg.data.split("\r\n"):
                    if not line:
                        continue
                    if line.startswith("PING"):
                        await ws.send_str("PONG" + line[4:])
                        continue
                    joined = await self._irc_line(line, joined)

    async def _irc_line(self, line: str, joined: bool) -> bool:
        tags, prefix, command, params, trailing = parse_irc(line)
        if command == "ROOMSTATE" and not joined:
            self.connected(self.login)
            return True
        if command == "PRIVMSG":
            msg = irc_message(tags, prefix, trailing)
            msg.channel = self.login
            self.emit(msg)
        elif command == "USERNOTICE":
            kind = _USERNOTICE_EVENTS.get(tags.get("msg-id", ""))
            if kind:
                msg = irc_message(tags, prefix, trailing)
                msg.event_type, msg.paid_kind = kind, kind  # a notice, not money
                msg.superchat = _tag_value(tags.get("system-msg", ""))[:80]
                self.emit(msg)
        elif command == "CLEARMSG":
            self.retract(message_id=tags.get("target-msg-id", ""))
        elif command == "CLEARCHAT" and tags.get("target-user-id"):
            self.retract(author_id=tags["target-user-id"])
        elif command == "NOTICE":
            notice = tags.get("msg-id", "")
            if notice in ("msg_channel_suspended", "tos_ban", "msg_banned"):
                raise FatalError(trailing or "This channel is unavailable.", "not-found")
            if "authentication failed" in trailing.lower():
                raise TransientError("Twitch refused the guest login")
        elif command == "RECONNECT":
            raise TransientError("Twitch asked to reconnect")
        return joined

    # -- EventSub (official) ---------------------------------------------------------

    async def _helix(self, method: str, path: str, account: dict, **kw) -> tuple[int, dict]:
        http = await self._http()
        headers = {"Authorization": f"Bearer {account['access_token']}", "Client-Id": account.get("client_id", "")}
        async with http.request(method, f"{self.api_base}{path}", headers=headers, **kw) as resp:
            if resp.status == 429:
                raise RateLimited("Twitch rate limit", retry_after(resp.headers, 30))
            try:
                data = await resp.json(content_type=None)
            except ValueError:
                data = {}
            return resp.status, data or {}

    async def _broadcaster(self, account: dict) -> tuple[str, str]:
        status, data = await self._helix("GET", "/helix/users", account, params={"login": self.login})
        if status == 401:
            raise AuthRequired("The Twitch login expired. Connect the account again.")
        if status != 200:
            raise TransientError(f"Twitch users: HTTP {status}")
        users = data.get("data") or []
        if not users:
            raise FatalError(f"Twitch channel '{self.login}' not found.", "not-found")
        return str(users[0]["id"]), users[0].get("display_name") or self.login

    async def _subscribe(self, account: dict, session_id: str, broadcaster: str) -> None:
        for kind in _SUBSCRIPTIONS:
            body = {"type": kind, "version": "1", "transport": {"method": "websocket", "session_id": session_id},
                    "condition": {"broadcaster_user_id": broadcaster, "user_id": account["user_id"]}}
            status, data = await self._helix("POST", "/helix/eventsub/subscriptions", account, json=body)
            if status in (200, 201, 202, 409):
                continue
            if status == 401:
                raise AuthRequired("The Twitch login expired. Connect the account again.")
            if status == 403 and kind != "channel.chat.message":
                continue  # optional extras (e.g. moderation events) must not block the chat
            raise FatalError(str(data.get("message") or f"Twitch refused {kind} (HTTP {status})"), "subscribe-failed")

    async def _welcome(self, ws) -> dict:
        welcome = await ws.receive_json(timeout=15)
        if (welcome.get("metadata") or {}).get("message_type") != "session_welcome":
            raise TransientError("EventSub: no welcome message")
        return welcome["payload"]["session"]

    async def _eventsub(self) -> None:
        http = await self._http()
        auth = self.auth()
        account = await auth.ensure(http, force=True)  # Twitch requires validating at start
        broadcaster, display = await self._broadcaster(account)
        ws = await http.ws_connect(self.eventsub_url, heartbeat=None, max_msg_size=1 << 20)
        try:
            session = await self._welcome(ws)
            await self._subscribe(account, session["id"], broadcaster)  # within 10 s of the welcome
            self.connected(display)
            while True:
                keepalive = float(session.get("keepalive_timeout_seconds") or 10)
                url = await self._eventsub_loop(ws, keepalive, auth)
                # session_reconnect: open the new socket first; subscriptions move with it
                new = await http.ws_connect(url, heartbeat=None, max_msg_size=1 << 20)
                try:
                    session = await self._welcome(new)
                except BaseException:
                    await new.close()
                    raise
                await ws.close()
                ws = new
        finally:
            await ws.close()

    async def _eventsub_loop(self, ws, keepalive: float, auth: TwitchAuth) -> str:
        """Read notifications; returns a reconnect URL when Twitch asks to move."""
        http = await self._http()
        validated = time.monotonic()
        while True:
            try:
                msg = await ws.receive(timeout=keepalive + 5)
            except asyncio.TimeoutError:
                raise TransientError("EventSub keepalive missed") from None
            if msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.CLOSING, aiohttp.WSMsgType.ERROR):
                code = ws.close_code or 0
                if code == 4004:
                    raise TransientError("EventSub reconnect grace time expired")
                raise TransientError(f"EventSub closed ({code})")
            if msg.type != aiohttp.WSMsgType.TEXT:
                continue
            data = msg.json()
            kind = (data.get("metadata") or {}).get("message_type")
            payload = data.get("payload") or {}
            if kind == "notification":
                self._notification(payload.get("subscription") or {}, payload.get("event") or {})
            elif kind == "session_reconnect":
                return payload["session"]["reconnect_url"]
            elif kind == "revocation":
                status = (payload.get("subscription") or {}).get("status", "")
                if status in ("authorization_revoked", "user_removed"):
                    raise AuthRequired("Twitch revoked the chat permission. Connect the account again.")
                raise TransientError(f"subscription revoked: {status}")
            if time.monotonic() - validated > 3600:  # hourly validation required by Twitch
                await auth.ensure(http, force=True)
                validated = time.monotonic()

    def _notification(self, subscription: dict, event: dict) -> None:
        kind = subscription.get("type", "")
        if kind == "channel.chat.message":
            msg = eventsub_message(event)
            msg.channel = event.get("broadcaster_user_name", "")
            self.emit(msg)
        elif kind == "channel.chat.notification":
            notice = _NOTICE_EVENTS.get(event.get("notice_type", ""))
            if notice:
                msg = eventsub_message(event)
                msg.event_type, msg.paid_kind = notice, notice  # a notice, not money
                msg.superchat = (event.get("system_message") or "")[:80]
                self.emit(msg)
        elif kind == "channel.chat.message_delete":
            self.retract(message_id=event.get("message_id", ""))
        elif kind == "channel.chat.clear_user_messages":
            self.retract(author_id=str(event.get("target_user_id", "")))

    # -- stream information ---------------------------------------------------------------

    async def metadata(self) -> StreamMetadata:
        """Title, category and tags from the official Helix API (needs the connected account)."""
        md = StreamMetadata(self.source.id, "twitch", method="Twitch Helix API (official)",
                            url=f"https://www.twitch.tv/{self.login}", channel=self.login)
        auth = self.auth()
        has = bool(await asyncio.to_thread(auth.account)) if self.ctx.credentials is not None else False
        if not has or not client_id(self.ctx.apps):
            md.ok, md.code = False, "auth-required"
            md.detail = "Connect a Twitch account (Settings › Accounts) to read the title and category."
            return md
        try:
            http = await self._http()
            account = await auth.ensure(http)
            broadcaster, display = await self._broadcaster(account)
            status, data = await self._helix("GET", "/helix/channels", account, params={"broadcaster_id": broadcaster})
            if status != 200:
                raise TransientError(f"Twitch channels: HTTP {status}")
            info = (data.get("data") or [{}])[0]
            _, streams = await self._helix("GET", "/helix/streams", account, params={"user_id": broadcaster})
        finally:
            await self.close()
        md.channel = info.get("broadcaster_name") or display
        md.title = info.get("title") or ""
        md.category = info.get("game_name") or ""
        md.tags = [str(t) for t in info.get("tags") or []]
        md.live = bool(streams.get("data"))
        md.detail = "Twitch does not publish a channel description through this API."
        return md

    # -- test connection ----------------------------------------------------------------

    async def probe(self) -> ProbeResult:
        try:
            if await self._use_account():
                http = await self._http()
                account = await self.auth().ensure(http, force=True)
                _, display = await self._broadcaster(account)
                return ProbeResult(True, "ready", channel=display)
            return await self._probe_irc()
        except (AuthRequired, Unsupported, FatalError) as e:
            return ProbeResult(False, e.code, str(e))
        except (aiohttp.ClientError, OSError, asyncio.TimeoutError, TransientError) as e:
            return ProbeResult(False, "network", type(e).__name__)

    async def _probe_irc(self) -> ProbeResult:
        """Join as a guest: Twitch sends ROOMSTATE only for channels that exist."""
        http = await self._http()
        async with http.ws_connect(self.irc_url, heartbeat=None) as ws:
            await ws.send_str("CAP REQ :twitch.tv/tags twitch.tv/commands")
            await ws.send_str(f"NICK justinfan{random.randint(10000, 99999)}")
            await ws.send_str(f"JOIN #{self.login}")
            deadline = time.monotonic() + float(self.ctx.extra.get("probe_wait", 8))
            while time.monotonic() < deadline:
                try:
                    msg = await ws.receive(timeout=max(0.1, deadline - time.monotonic()))
                except asyncio.TimeoutError:
                    break
                if msg.type != aiohttp.WSMsgType.TEXT:
                    break
                for line in msg.data.split("\r\n"):
                    if parse_irc(line)[2] == "ROOMSTATE":
                        return ProbeResult(True, "ready", channel=self.login)
        return ProbeResult(False, "not-found", f"Twitch channel '{self.login}' not found.")
