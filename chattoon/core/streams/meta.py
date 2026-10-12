"""Facebook and Instagram live comments through Meta's Graph API (support: limited).

Meta offers no anonymous way to read a live chat, so both sources need an access token
the streamer pastes once (Settings › Accounts) from Meta's Graph API Explorer or Access
Token Tool, created with their own Meta app ("bring your own app": apps in Development
mode work for people with a role on the app; public apps need App Review for the Live
Video API). ChatToon cannot ship an app secret and never asks for a password. The token
is kept in the keyring under ``meta/token`` as ``{"access_token": …, "kind": "user" |
"page" | "instagram"}`` (``kind`` optional) and only ever travels in the
``Authorization`` header.

* Facebook — only **Pages** can be read; lives on personal profiles have no API. A user
  token is exchanged for the Page's own token through ``/me/accounts`` (kept in memory
  only), because commenter names come only with a Page token. The live is found with
  ``/{page}/live_videos?broadcast_status=["LIVE"]`` or given directly as ``video:<id>``
  (a pasted video link), and ``/{live-video}/comments`` is polled with ``since``.
  Permissions: ``pages_show_list``, ``pages_read_engagement`` and/or
  ``pages_read_user_content``.
* Instagram — a professional (Business/Creator) account linked to a Facebook Page the
  token manages. ``/{ig-user}/live_media`` returns the live broadcasting now and
  ``/{ig-media}/comments`` its newest 50 top-level comments (no time filter, so new ids
  are picked out of each page). Permissions: ``instagram_basic``,
  ``instagram_manage_comments`` (or ``instagram_business_manage_comments``),
  ``pages_read_engagement``, ``pages_show_list``. The ``live_comments`` webhook would be
  push-based but needs a public HTTPS server and Advanced Access: not implemented.

Polling is conservative: comments every ``poll`` seconds (option, 3–60; Facebook 5,
Instagram 6), several times slower when Meta's usage headers pass 75 %, and the live
status is re-checked only every 30 s. Throttling errors become :class:`RateLimited`
with the wait Meta announces.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import unicodedata
from datetime import datetime

import aiohttp

from ..credentials import REDACTOR
from ..messages import ChatMessage
from .base import (AuthRequired, Connector, ConnectorError, FatalError, LiveEnded, NotLive, ProbeResult, RateLimited,
                   TransientError, Unsupported)

log = logging.getLogger(__name__)

GRAPH_BASE = "https://graph.facebook.com/v26.0"
CREDENTIAL = "meta/token"
STATUS_EVERY = 30.0  # seconds of polling between two "is it still live?" checks
SLOW_USAGE = 75.0  # % of a Meta rate-limit budget after which polling slows down

AUTH_CODES = {102, 190, 463, 467}
RATE_CODES = {4, 17, 32, 613} | set(range(80001, 80015))
TRANSIENT_CODES = {1, 2, 341, 368}
NO_TOKEN = "Paste a Meta access token first (Settings › Accounts)."
FB_PERMISSIONS = "pages_read_engagement / pages_read_user_content"
IG_PERMISSIONS = "instagram_basic, instagram_manage_comments, pages_read_engagement"


def poll_option(options: dict, default: float, low: float, high: float) -> float:
    """The ``poll`` option (seconds) clamped to what the platform tolerates."""
    try:
        value = float(options.get("poll", default))
    except (TypeError, ValueError):
        value = default
    return min(high, max(low, value if value == value else default))


def usage(headers) -> tuple[float, float]:
    """Highest percentage in Meta's usage headers and minutes until access returns."""
    top = regain = 0.0
    for name in ("X-App-Usage", "X-Page-Usage", "X-Business-Use-Case-Usage"):
        raw = headers.get(name) if headers else None
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except ValueError:
            continue
        entries: list = []
        if isinstance(data, dict) and {"call_count", "total_time", "total_cputime"} & data.keys():
            entries = [data]
        elif isinstance(data, dict):  # business use case: {object id: [{type, call_count, …}]}
            for value in data.values():
                entries += value if isinstance(value, list) else [value]
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            for key in ("call_count", "total_time", "total_cputime"):
                try:
                    top = max(top, float(entry.get(key) or 0))
                except (TypeError, ValueError):
                    pass
            try:
                regain = max(regain, float(entry.get("estimated_time_to_regain_access") or 0))
            except (TypeError, ValueError):
                pass
    return top, regain


def parse_time(value) -> float:
    """Graph timestamps ("2026-10-12T15:04:05+0000") -> unix seconds (0 when unreadable)."""
    try:
        return datetime.strptime(str(value), "%Y-%m-%dT%H:%M:%S%z").timestamp()
    except ValueError:
        return 0.0


def _norm(text) -> str:
    folded = unicodedata.normalize("NFKD", str(text or "").casefold())
    return "".join(c for c in folded if c.isalnum())


class _GraphConnector(Connector):
    """Token handling, Graph requests, error mapping and adaptive polling."""

    support = "limited"
    reconnect_when_ended = True
    default_poll = 5.0
    wait_poll = 30.0  # live discovery every 30 s (cheap: one request)
    permissions = FB_PERMISSIONS

    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)
        self.graph_base = self.ctx.extra.get("graph_base", GRAPH_BASE).rstrip("/")
        self.poll = poll_option(self.source.options, self.default_poll, 3.0, 60.0)
        self.usage = 0.0  # last percentage reported by Meta
        self._session: aiohttp.ClientSession | None = None
        self._secrets: set[str] = set()
        self._cursors: dict[str, dict] = {}  # live id -> {"since", "primed"}, kept across reconnections

    async def _http(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30),
                                                  headers={"User-Agent": self.ctx.user_agent})
        return self._session

    async def close(self) -> None:
        if self._session is not None and not self._session.closed:
            await self._session.close()

    def _secret(self, value: str) -> str:
        if value:
            self._secrets.add(value)
            REDACTOR.add(value)  # page tokens never reach the keyring: register them for log redaction
        return value

    def _scrub(self, text: str) -> str:
        for value in self._secrets:
            text = text.replace(value, "***")
        return text[:200]

    async def _credential(self) -> tuple[str, str]:
        store = self.ctx.credentials
        cred = await asyncio.to_thread(store.get, CREDENTIAL) if store is not None else None
        token = str((cred or {}).get("access_token") or "").strip()
        if not token:
            raise AuthRequired(NO_TOKEN)
        return self._secret(token), str(cred.get("kind") or "").strip().lower()

    async def graph(self, path: str, token: str, params: dict | None = None) -> dict:
        """GET one Graph object or edge; raises the matching :class:`ConnectorError`."""
        http = await self._http()
        async with http.get(f"{self.graph_base}/{path.lstrip('/')}", params=params or {},
                            headers={"Authorization": f"Bearer {token}"}) as resp:
            self.usage, regain = usage(resp.headers)
            try:
                data = await resp.json(content_type=None)
            except ValueError:
                data = None
            if not isinstance(data, dict):
                data = {}
            error = data.get("error")
            if resp.status == 200 and not error:
                return data
            raise self._error(resp.status, error if isinstance(error, dict) else {}, regain)

    def _error(self, status: int, error: dict, regain: float) -> ConnectorError:
        try:
            code = int(error.get("code") or 0)
        except (TypeError, ValueError):
            code = 0
        detail = self._scrub(str(error.get("message") or f"HTTP {status}"))
        if code in AUTH_CODES or (status == 401 and not code):
            return AuthRequired("The Meta access token is invalid or expired. Paste a new one (Settings › Accounts).")
        if code in RATE_CODES or status == 429:
            wait = regain * 60 if regain > 0 else 300.0
            return RateLimited(f"Meta rate limit reached (#{code or status}).", wait)
        if code == 10 or 200 <= code <= 299:
            return AuthRequired(f"The Meta token lacks a permission ({self.permissions}): {detail}")
        if code == 100:
            return FatalError(f"Not found or not accessible with this token: {detail}", "not-found")
        if status >= 500 or code in TRANSIENT_CODES or error.get("is_transient"):
            return TransientError(f"Meta Graph API: HTTP {status} (#{code})")
        return FatalError(f"Meta Graph API error #{code or status}: {detail}", "graph-error")

    async def _pages(self, token: str) -> list[dict]:
        """Pages the user token manages (with their own tokens and linked Instagram)."""
        data = await self.graph("me/accounts", token, {
            "fields": "id,name,username,access_token,instagram_business_account{id,username}", "limit": "100"})
        pages = [p for p in data.get("data") or [] if isinstance(p, dict) and p.get("id")]
        for page in pages:
            self._secret(str(page.get("access_token") or ""))
        return pages

    def interval(self) -> float:
        """Seconds until the next poll: slower while Meta reports a busy budget."""
        if self.usage >= 90:
            return max(30.0, self.poll * 4)
        if self.usage > SLOW_USAGE:
            return max(15.0, self.poll * 3)
        return self.poll

    def _cursor(self, live_id: str) -> dict:
        return self._cursors.setdefault(live_id, {"since": 0, "primed": False})

    async def _probe(self) -> ProbeResult:
        raise NotImplementedError

    async def probe(self) -> ProbeResult:
        try:
            return await self._probe()
        except LiveEnded as e:
            return ProbeResult(False, "ended", str(e), self.status.channel)
        except RateLimited as e:
            return ProbeResult(False, "rate-limited", str(e))
        except FatalError as e:
            return ProbeResult(False, "not-found" if e.code == "not-found" else e.code, str(e))
        except (AuthRequired, Unsupported) as e:
            return ProbeResult(False, e.code, str(e))
        except (aiohttp.ClientError, OSError, asyncio.TimeoutError, TransientError) as e:
            return ProbeResult(False, "network", type(e).__name__)
        finally:
            await self.close()


# -- Facebook ---------------------------------------------------------------------------

class FacebookConnector(_GraphConnector):
    """A Facebook Page (waits for each live) or one live video (``video:<id>``)."""

    platform = "facebook"
    label = "Facebook"
    default_poll = 5.0
    permissions = FB_PERMISSIONS

    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)
        from .urls import detect

        target = detect(self.source.target, "facebook").target  # ValueError: bad page or link
        self.video_id = target.removeprefix("video:") if target.startswith("video:") else ""
        self.page = "" if self.video_id else target
        self.reconnect_when_ended = not self.video_id  # a Page waits for its next live
        self._video_fields = ""

    async def _page(self) -> dict:
        """{"id", "name", "token"}: the Page to read and the token to read it with."""
        token, kind = await self._credential()
        me = await self.graph("me", token, {"fields": "id,name"})
        if kind != "page":
            try:
                pages = await self._pages(token)
            except FatalError as e:
                if kind == "user" or e.code != "not-found":
                    raise
                pages = None  # "nonexisting field (accounts) on node type (Page)": a Page token
            if pages is not None:
                return await self._pick(me, pages, token)
        return await self._own_page(me, token)

    async def _pick(self, me: dict, pages: list[dict], token: str) -> dict:
        def page(p: dict) -> dict:
            return {"id": str(p["id"]), "name": p.get("name") or p.get("username") or str(p["id"]),
                    "token": p.get("access_token") or token}

        if self.video_id:
            if len(pages) == 1:
                return page(pages[0])
            owner = await self._video_owner(token)
            for p in pages:
                if str(p["id"]) == owner:
                    return page(p)
            log.info("facebook source %s: video owner not among the managed Pages; commenter names may be hidden",
                     self.source.id)
            return {"id": owner, "name": "", "token": token}
        wanted = _norm(self.page)
        for p in pages:
            if wanted in (_norm(p.get("id")), _norm(p.get("username")), _norm(p.get("name"))):
                return page(p)
        if not pages:
            raise AuthRequired("This Meta token manages no Facebook Page (grant pages_show_list) or paste a Page "
                               "token (Settings › Accounts).")
        if wanted in (_norm(me.get("id")), _norm(me.get("name"))):
            raise Unsupported("This is a personal profile: Facebook does not let apps read the comments of lives "
                              "on personal profiles. Go live on a Facebook Page you manage instead.")
        names = ", ".join(str(p.get("name") or p.get("id")) for p in pages[:5])
        raise Unsupported(f"'{self.page}' is not a Page this token manages ({names}). ChatToon reads only lives "
                          "of Facebook Pages you manage; lives on personal profiles cannot be read.")

    async def _video_owner(self, token: str) -> str:
        try:
            data = await self.graph(self.video_id, token, {"fields": "from{id,name}"})
        except (FatalError, AuthRequired):
            return ""
        return str((data.get("from") or {}).get("id") or "")

    async def _own_page(self, me: dict, token: str) -> dict:
        page = {"id": str(me.get("id") or ""), "name": me.get("name") or "", "token": token}
        if self.video_id or _norm(self.page) in (_norm(page["id"]), _norm(page["name"])):
            return page
        try:  # the target may be the Page's username
            found = await self.graph(self.page, token, {"fields": "id"})
        except FatalError:
            found = {}
        if str(found.get("id") or "") == page["id"]:
            return page
        raise AuthRequired(f"This token belongs to the Page '{page['name']}', not to '{self.page}'. Paste a token "
                           "of that Page (Settings › Accounts).")

    async def _video_state(self, token: str, video_id: str) -> str:
        """LIVE, LIVE_STOPPED, VOD, SCHEDULED_…: ``status`` of a LiveVideo, ``live_status`` of a Video."""
        choices = [self._video_fields] if self._video_fields else ["live_status", "status"]
        for fields in choices:
            try:
                data = await self.graph(video_id, token, {"fields": f"id,{fields}"})
            except FatalError as e:
                if e.code == "not-found" and fields != choices[-1]:
                    continue  # a LiveVideo id has no live_status field
                raise
            self._video_fields = fields
            value = data.get(fields)
            return value.upper() if isinstance(value, str) else "LIVE"  # unknown: just read the comments
        return "LIVE"

    async def _find_live(self, page: dict) -> str:
        """Id of the live video to read (NotLive / LiveEnded otherwise)."""
        if self.video_id:
            state = await self._video_state(page["token"], self.video_id)
            if state == "LIVE":
                return self.video_id
            if "SCHEDULED" in state or state in ("UNPUBLISHED", "PREVIEW"):
                raise NotLive("This live video has not started yet.")
            raise LiveEnded("This live video has ended.")
        data = await self.graph(f"{page['id']}/live_videos", page["token"], {
            "broadcast_status": '["LIVE"]', "fields": "id,status,title"})
        for video in data.get("data") or []:
            if isinstance(video, dict) and video.get("id") and str(video.get("status") or "LIVE").upper() == "LIVE":
                self._video_fields = "status"
                return str(video["id"])
        raise NotLive(f"The Page '{page['name'] or self.page}' is not live right now.")

    async def session(self) -> None:
        page = await self._page()
        self.status.channel = page["name"] or self.source.label or self.page or f"video {self.video_id}"
        live = await self._find_live(page)
        self.connected()
        await self._read(page, live)

    async def _read(self, page: dict, live: str) -> None:
        cursor = self._cursor(live)
        elapsed = 0.0
        while True:
            params = {"filter": "stream", "order": "reverse_chronological", "live_filter": "no_filter",
                      "fields": "id,message,created_time,from{id,name}", "limit": "100"}
            if cursor["since"]:
                params["since"] = str(cursor["since"])
            try:
                data = await self.graph(f"{live}/comments", page["token"], params)
            except FatalError as e:
                if e.code == "not-found" and not self.video_id:
                    return  # the live video is gone: wait for the next one
                raise
            skip = self.ctx.skip_backlog and not cursor["primed"]
            cursor["primed"] = True
            for item in reversed([c for c in data.get("data") or [] if isinstance(c, dict) and c.get("id")]):
                stamp = parse_time(item.get("created_time"))
                cursor["since"] = max(cursor["since"], int(stamp))
                text = str(item.get("message") or "")
                if skip or not text.strip():
                    self.remember(str(item["id"]))
                    continue
                author = item.get("from") or {}
                self.emit(ChatMessage(
                    id=str(item["id"]), author=author.get("name") or "Facebook", author_id=str(author.get("id") or ""),
                    text=text, timestamp=stamp or time.time(),
                    is_owner=bool(page["id"]) and str(author.get("id") or "") == page["id"]))
            delay = self.interval()
            await self._sleep(delay)
            elapsed += delay
            if elapsed >= STATUS_EVERY:
                elapsed = 0.0
                if await self._video_state(page["token"], live) != "LIVE":
                    return

    async def _probe(self) -> ProbeResult:
        page = await self._page()
        self.status.channel = page["name"] or self.page or f"video {self.video_id}"
        try:
            await self._find_live(page)
        except NotLive as e:
            return ProbeResult(True, "offline", str(e), self.status.channel)
        return ProbeResult(True, "live", channel=self.status.channel)


# -- Instagram ----------------------------------------------------------------------------

class InstagramConnector(_GraphConnector):
    """An Instagram professional account: waits for each live and reads its comments."""

    platform = "instagram"
    label = "Instagram"
    default_poll = 6.0
    permissions = IG_PERMISSIONS
    PAGE_SIZE = 50  # what /{ig-media}/comments returns at most

    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)
        from .urls import detect

        self.username = detect(self.source.target, "instagram").target.lstrip("@")  # ValueError: bad user

    def _matches(self, ig: dict) -> bool:
        return self.username in (str(ig.get("username") or "").lower(), str(ig.get("id") or ""))

    def _not_linked(self) -> Unsupported:
        return Unsupported(f"@{self.username} is not linked to a Facebook Page this token manages. Instagram lives "
                           "can only be read from a professional (Business or Creator) account linked to a Page.")

    async def _account(self) -> dict:
        """{"id", "username", "token"} of the Instagram professional account."""
        token, kind = await self._credential()
        if kind not in ("page", "instagram"):
            try:
                pages = await self._pages(token)
            except FatalError as e:
                if kind == "user" or e.code != "not-found":
                    raise
                pages = None  # not a user token
            if pages is not None:
                for page in pages:
                    ig = page.get("instagram_business_account") or {}
                    if ig.get("id") and self._matches(ig):
                        return {"id": str(ig["id"]), "username": ig.get("username") or self.username, "token": token}
                if not pages:
                    raise AuthRequired("This Meta token manages no Facebook Page (grant pages_show_list) or paste a "
                                       "Page token (Settings › Accounts).")
                raise self._not_linked()
        if kind != "instagram":
            try:  # a Page token: its linked Instagram account
                me = await self.graph("me", token, {"fields": "id,name,instagram_business_account{id,username}"})
            except FatalError as e:
                if kind == "page" or e.code != "not-found":
                    raise
                me = None  # not a Page either: an Instagram user token
            if me is not None:
                ig = me.get("instagram_business_account") or {}
                if ig.get("id") and self._matches(ig):
                    return {"id": str(ig["id"]), "username": ig.get("username") or self.username, "token": token}
                raise self._not_linked()
        me = await self.graph("me", token, {"fields": "id,username"})
        if me.get("id") and self._matches(me):
            return {"id": str(me["id"]), "username": me.get("username") or self.username, "token": token}
        raise AuthRequired(f"This token belongs to @{me.get('username') or '?'}, not to @{self.username}. Paste a "
                           "token of that account (Settings › Accounts).")

    async def _lives(self, account: dict) -> list[str]:
        data = await self.graph(f"{account['id']}/live_media", account["token"], {
            "fields": "id,media_type,media_product_type,username,timestamp"})
        return [str(m["id"]) for m in data.get("data") or [] if isinstance(m, dict) and m.get("id")]

    async def session(self) -> None:
        account = await self._account()
        self.status.channel = f"@{account['username']}"
        lives = await self._lives(account)
        if not lives:
            raise NotLive(f"@{account['username']} is not live on Instagram right now.")
        self.connected()
        await self._read(account, lives[0])

    async def _read(self, account: dict, media: str) -> None:
        cursor = self._cursor(media)
        elapsed = 0.0
        while True:
            data = await self.graph(f"{media}/comments", account["token"], {
                "fields": "id,text,username,timestamp,from{id,username}", "limit": str(self.PAGE_SIZE)})
            items = [c for c in data.get("data") or [] if isinstance(c, dict) and c.get("id")]
            fresh = [c for c in items if str(c["id"]) not in self._seen]
            skip = self.ctx.skip_backlog and not cursor["primed"]
            if cursor["primed"] and len(fresh) >= self.PAGE_SIZE:
                log.info("instagram source %s: more than %d comments between two polls; some were missed",
                         self.source.id, self.PAGE_SIZE)
            cursor["primed"] = True
            for item in reversed(fresh):  # the API answers newest first
                text = str(item.get("text") or "")
                if skip or not text.strip():
                    self.remember(str(item["id"]))
                    continue
                author = item.get("from") or {}
                name = item.get("username") or author.get("username") or "Instagram"
                author_id = str(author.get("id") or "")
                self.emit(ChatMessage(
                    id=str(item["id"]), author=name, author_id=author_id, text=text,
                    timestamp=parse_time(item.get("timestamp")) or time.time(),
                    is_owner=author_id == account["id"] or name.lower() == account["username"].lower()))
            delay = self.interval()
            if len(fresh) >= self.PAGE_SIZE and not skip:
                delay = max(3.0, delay / 2)  # a busy chat: the page is full, look again sooner
            await self._sleep(delay)
            elapsed += delay
            if elapsed >= STATUS_EVERY:
                elapsed = 0.0
                if media not in await self._lives(account):
                    return

    async def _probe(self) -> ProbeResult:
        account = await self._account()
        self.status.channel = f"@{account['username']}"
        if await self._lives(account):
            return ProbeResult(True, "live", channel=self.status.channel)
        return ProbeResult(True, "offline", f"@{account['username']} is not live right now.", self.status.channel)
