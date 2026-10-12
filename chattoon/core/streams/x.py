"""X (Twitter): replies to the post announcing the live (support: limited).

X has **no API for the chat of live video broadcasts**, and Spaces have no chat API
either (``GET /2/spaces`` returns only metadata and shared posts). What can be read
honestly is the conversation under a post: viewers replying to "I'm live!" are read like
a chat. A ``broadcast:<id>`` source therefore stops at once as *unsupported* (``no-api``)
and a ``post:<id>`` source polls the official recent search:

``GET /2/tweets/search/recent?query=conversation_id:<id>&since_id=<last>`` with the
streamer's own app-only Bearer Token (keyring ``x/bearer`` = ``{"bearer_token": …}``,
created in the X developer console; it only travels in the ``Authorization`` header).

Cost: the X API is pay-per-use in 2026 — about US$ 0.005 per post read (posts are
billed once per UTC day). Polling is therefore slow on purpose: option ``poll``
(seconds, 15–300, default 20), ``since_id`` so every reply is read once, and at start
the backlog is not even requested (``start_time`` = now) when it would be skipped. The
search covers the last 7 days only: replies to an older post never show up. The
app limit (450 requests / 15 min) is respected through ``x-rate-limit-*`` headers.
"""

from __future__ import annotations

import asyncio
import re
import time
from datetime import datetime, timezone

import aiohttp

from ..messages import ChatMessage
from .base import (AuthRequired, Connector, ConnectorError, FatalError, ProbeResult, RateLimited, TransientError,
                   Unsupported, retry_after)

API_BASE = "https://api.x.com"
CREDENTIAL = "x/bearer"
NO_TOKEN = "Paste an X API Bearer Token first (Settings › Accounts)."
NO_API = ("X offers no API to read the chat of live video broadcasts (nor of Spaces). Use the link of the post "
          "announcing the live instead: ChatToon reads the replies to it.")
PLAN = ("The X API refused the request for billing reasons: the app must belong to a project with pay-per-use "
        "credits (developer console › Billing).")
_PLAN_HINTS = ("client-not-enrolled", "client_not_enrolled", "creditsdepleted", "credits", "usage-capped",
               "usagecapexceeded", "not enrolled", "billing")
_LEADING_MENTIONS = re.compile(r"^(?:@\w{1,15}\s+)+")


def poll_option(options: dict, default: float, low: float, high: float) -> float:
    """The ``poll`` option (seconds) clamped to what the API (and the bill) tolerates."""
    try:
        value = float(options.get("poll", default))
    except (TypeError, ValueError):
        value = default
    return min(high, max(low, value if value == value else default))


def iso(seconds: float) -> str:
    return datetime.fromtimestamp(seconds, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_time(value) -> float:
    try:
        return datetime.strptime(str(value), "%Y-%m-%dT%H:%M:%S.%f%z").timestamp()
    except ValueError:
        try:
            return datetime.strptime(str(value), "%Y-%m-%dT%H:%M:%S%z").timestamp()
        except ValueError:
            return 0.0


class XConnector(Connector):
    platform = "x"
    label = "X"
    support = "limited"
    reconnect_when_ended = False  # a conversation never "ends": read until stopped

    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)
        from .urls import detect

        kind, _, value = detect(self.source.target, "x").target.partition(":")  # ValueError: bad link
        self.kind, self.post_id = kind, value
        self.api_base = self.ctx.extra.get("x_api_base", API_BASE).rstrip("/")
        self.poll = poll_option(self.source.options, 20.0, 15.0, 300.0)
        self.since_id = ""
        self.start_time = ""  # first window when the backlog is skipped (nothing old is read nor billed)
        self.root_author = ""
        self.remaining: int | None = None
        self.reset_at = 0.0
        self._session: aiohttp.ClientSession | None = None
        self._token = ""

    async def _http(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30),
                                                  headers={"User-Agent": self.ctx.user_agent})
        return self._session

    async def close(self) -> None:
        if self._session is not None and not self._session.closed:
            await self._session.close()

    async def _bearer(self) -> str:
        store = self.ctx.credentials
        cred = await asyncio.to_thread(store.get, CREDENTIAL) if store is not None else None
        token = str((cred or {}).get("bearer_token") or "").strip()
        if not token:
            raise AuthRequired(NO_TOKEN)
        self._token = token
        return token

    def _scrub(self, text: str) -> str:
        return (text.replace(self._token, "***") if self._token else text)[:200]

    async def api(self, path: str, token: str, params: dict) -> dict:
        """GET an X API v2 endpoint; raises the matching :class:`ConnectorError`."""
        http = await self._http()
        async with http.get(f"{self.api_base}{path}", params=params,
                            headers={"Authorization": f"Bearer {token}"}) as resp:
            self._track(resp.headers)
            body = await resp.text()
            if resp.status == 200:
                try:
                    data = await resp.json(content_type=None)
                except ValueError:
                    raise TransientError("X API: unreadable answer") from None
                return data if isinstance(data, dict) else {}
            raise self._error(resp.status, body, resp.headers)

    def _error(self, status: int, body: str, headers) -> ConnectorError:
        if status == 429:
            return RateLimited("X API rate limit reached.", retry_after(headers, 900.0))
        if status == 401:
            return AuthRequired("X did not accept the Bearer Token. Paste a new one (Settings › Accounts).")
        lowered = body.lower()
        if status == 402 or (status == 403 and any(hint in lowered for hint in _PLAN_HINTS)):
            return Unsupported(PLAN, "plan-required")
        if status == 403:
            return AuthRequired("X refused access to the search (HTTP 403). Check the app's project and "
                                "permissions in the developer console.")
        if status == 404:
            return FatalError("Post not found.", "not-found")
        if status >= 500:
            return TransientError(f"X API: HTTP {status}")
        match = re.search(r'"(?:detail|message)"\s*:\s*"([^"]{1,160})', body)
        return FatalError(f"X API: HTTP {status} {self._scrub(match.group(1)) if match else ''}".strip(),
                          "bad-request")

    def _track(self, headers) -> None:
        try:
            self.remaining = int(headers.get("x-rate-limit-remaining"))
            self.reset_at = float(headers.get("x-rate-limit-reset"))
        except (TypeError, ValueError):
            self.remaining = None

    def interval(self) -> float:
        """The configured poll, stretched so the rest of the window lasts until the reset."""
        delay = self.poll
        left = self.reset_at - time.time()
        if self.remaining is not None and left > 0:
            delay = max(delay, left + 1 if self.remaining <= 1 else left / self.remaining)
        return min(900.0, delay)

    # -- session -------------------------------------------------------------------------

    async def session(self) -> None:
        if self.kind != "post":
            raise Unsupported(NO_API, "no-api")
        token = await self._bearer()
        if not self.since_id and not self.start_time and self.ctx.skip_backlog:
            self.start_time = iso(time.time())
        await self._poll(token)
        self.connected(self.status.channel or self.source.label or f"post {self.post_id}")
        while True:
            await self._sleep(self.interval())
            await self._poll(token)

    async def _poll(self, token: str) -> None:
        params = {"query": f"conversation_id:{self.post_id}", "tweet.fields": "author_id,created_at,conversation_id",
                  "expansions": "author_id", "user.fields": "username,name,verified", "max_results": "100"}
        if self.since_id:
            params["since_id"] = self.since_id
        elif self.start_time:
            params["start_time"] = self.start_time
        data = await self.api("/2/tweets/search/recent", token, params)
        users = {str(u.get("id")): u for u in (data.get("includes") or {}).get("users") or [] if isinstance(u, dict)}
        posts = [p for p in data.get("data") or [] if isinstance(p, dict) and str(p.get("id") or "").isdigit()]
        for post in sorted(posts, key=lambda p: int(p["id"])):  # ids grow with time: oldest first
            pid = str(post["id"])
            if not self.since_id or int(pid) > int(self.since_id):
                self.since_id = pid
            user = users.get(str(post.get("author_id") or ""), {})
            if pid == self.post_id:  # the announcement itself
                self.root_author = str(post.get("author_id") or "")
                if user.get("username") and not self.source.label and self.status.channel != f"@{user['username']}":
                    self.status.channel = f"@{user['username']}"
                    if self.status.state == "connected":
                        self.connected()  # show the new name
                self.remember(pid)
                continue
            text = _LEADING_MENTIONS.sub("", str(post.get("text") or "")).strip()
            if not text:
                self.remember(pid)
                continue
            author_id = str(post.get("author_id") or "")
            self.emit(ChatMessage(
                id=pid, author=user.get("name") or user.get("username") or "X", author_id=author_id, text=text,
                timestamp=parse_time(post.get("created_at")) or time.time(), is_verified=bool(user.get("verified")),
                is_owner=bool(self.root_author) and author_id == self.root_author))
        newest = str((data.get("meta") or {}).get("newest_id") or "")
        if newest.isdigit() and (not self.since_id or int(newest) > int(self.since_id)):
            self.since_id = newest

    # -- test connection -------------------------------------------------------------------

    async def probe(self) -> ProbeResult:
        """Reads the post itself (one post read) instead of a search page (up to 10)."""
        if self.kind != "post":
            return ProbeResult(False, "unsupported", NO_API)
        try:
            token = await self._bearer()
            data = await self.api(f"/2/tweets/{self.post_id}", token, {
                "tweet.fields": "author_id,created_at", "expansions": "author_id", "user.fields": "username,name"})
        except RateLimited as e:
            return ProbeResult(False, "rate-limited", str(e))
        except (AuthRequired, Unsupported, FatalError) as e:
            return ProbeResult(False, e.code, str(e))
        except (aiohttp.ClientError, OSError, asyncio.TimeoutError, TransientError) as e:
            return ProbeResult(False, "network", type(e).__name__)
        finally:
            await self.close()
        post = data.get("data") or {}
        if not post:
            return ProbeResult(False, "not-found", "Post not found (deleted, private or a wrong link).")
        users = (data.get("includes") or {}).get("users") or [{}]
        channel = f"@{users[0].get('username')}" if users[0].get("username") else f"post {self.post_id}"
        age = time.time() - parse_time(post.get("created_at"))
        if parse_time(post.get("created_at")) and age > 7 * 86400:
            return ProbeResult(True, "ready", "The post is older than 7 days: X's search no longer shows its replies.",
                               channel)
        return ProbeResult(True, "ready", channel=channel)
