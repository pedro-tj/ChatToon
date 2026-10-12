"""YouTube Live chat reader.

Uses the same public endpoints as the chat pop-out window (``/live_chat`` page +
``youtubei/v1/live_chat/get_live_chat``) and polls at the interval the server asks for
(``timeoutMs``), so it is no more aggressive than having the chat open in a browser. No
login or API key from the user is needed. Messages are de-duplicated by their YouTube id.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from collections import OrderedDict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from urllib.parse import parse_qs, urlparse

import aiohttp

from .messages import ChatMessage

log = logging.getLogger(__name__)

_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
_UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
       "Chrome/140.0 Safari/537.36")
BASE = "https://www.youtube.com"
_PAID = {"liveChatPaidMessageRenderer": "superchat", "liveChatPaidStickerRenderer": "supersticker"}


class ChatError(Exception):
    """Unrecoverable problem: the chat cannot be read (disabled, not live, bad URL)."""


def extract_video_id(url: str) -> str:
    """Return the 11-character video id from any common YouTube URL (or a bare id)."""
    text = (url or "").strip()
    if _ID.match(text):
        return text
    if not re.match(r"^[a-z]+://", text, re.I):
        text = "https://" + text
    parsed = urlparse(text)
    host = (parsed.hostname or "").lower().removeprefix("www.").removeprefix("m.")
    candidate = ""
    if host == "youtu.be":
        candidate = parsed.path.strip("/").split("/")[0]
    elif host in ("youtube.com", "music.youtube.com", "studio.youtube.com", "gaming.youtube.com"):
        query = parse_qs(parsed.query)
        if "v" in query:
            candidate = query["v"][0]
        else:
            parts = [p for p in parsed.path.split("/") if p]
            if len(parts) >= 2 and parts[0] in ("live", "shorts", "embed", "v", "video"):
                candidate = parts[1]
    if not _ID.match(candidate):
        raise ValueError("Not a YouTube video or live URL")
    return candidate


@dataclass
class ChatStatus:
    state: str  # connecting | connected | reconnecting | ended | error | stopped
    detail: str = ""
    attempt: int = 0


def _runs_text(message: dict) -> str:
    parts = []
    for run in (message or {}).get("runs", []):
        if "text" in run:
            parts.append(run["text"])
        elif "emoji" in run:
            emoji = run["emoji"]
            # Standard emoji: emojiId is the character itself. Channel emotes
            # (":whistle-red-blow:") are noise for the AI and the voice.
            if not emoji.get("isCustomEmoji"):
                parts.append(emoji.get("emojiId", ""))
    if not parts:
        return (message or {}).get("simpleText", "")
    return "".join(parts)


def parse_actions(actions: list[dict]) -> list[ChatMessage]:
    """Turn InnerTube chat actions into messages (unknown item types are skipped)."""
    out: list[ChatMessage] = []
    for action in actions or []:
        item = (action.get("addChatItemAction") or {}).get("item") or {}
        for kind, r in item.items():
            if kind not in ("liveChatTextMessageRenderer", "liveChatPaidMessageRenderer",
                            "liveChatMembershipItemRenderer", "liveChatPaidStickerRenderer"):
                continue
            text = _runs_text(r.get("message") or {})
            if kind == "liveChatMembershipItemRenderer" and not text:
                text = _runs_text(r.get("headerSubtext") or {})
            badges = [b.get("liveChatAuthorBadgeRenderer", {}) for b in r.get("authorBadges", [])]
            icons = {(b.get("icon") or {}).get("iconType", "") for b in badges}
            member = any("customThumbnail" in b for b in badges) or kind == "liveChatMembershipItemRenderer"
            try:
                ts = int(r.get("timestampUsec", "0")) / 1e6
            except ValueError:
                ts = 0.0
            out.append(ChatMessage(
                id=r.get("id", ""),
                author=(r.get("authorName") or {}).get("simpleText", "").lstrip("@") or "?",
                author_id=r.get("authorExternalChannelId", ""),
                text=text,
                timestamp=ts,
                is_moderator="MODERATOR" in icons,
                is_owner="OWNER" in icons,
                is_verified="VERIFIED" in icons,
                is_member=member,
                superchat=(r.get("purchaseAmountText") or {}).get("simpleText", ""),
                event_type="paid" if kind in _PAID else "message",
                paid_kind=_PAID.get(kind, ""),
            ))
    return [m for m in out if m.id]


def _continuation(container: dict) -> tuple[str, int]:
    for entry in container.get("continuations", []):
        for data in entry.values():
            if isinstance(data, dict) and data.get("continuation"):
                return data["continuation"], int(data.get("timeoutMs", 5000))
    return "", 0


def parse_page(html: str) -> tuple[dict, list[ChatMessage], str, int]:
    """Extract the InnerTube config, backlog and first continuation from the pop-out page."""
    key = re.search(r'"INNERTUBE_API_KEY":"([^"]+)"', html)
    ctx = re.search(r'"INNERTUBE_CONTEXT":(\{.+?\}),"INNERTUBE_', html)
    data = re.search(r'(?:window\["ytInitialData"\]|var ytInitialData|ytInitialData)\s*=\s*(\{.+?\});\s*</script>',
                     html, re.S)
    if not (key and ctx and data):
        raise ChatError("YouTube returned an unexpected page (chat unavailable or the page format changed).")
    initial = json.loads(data.group(1))
    contents = initial.get("contents") or {}
    renderer = contents.get("liveChatRenderer")
    if not renderer:
        notice = _runs_text((contents.get("messageRenderer") or {}).get("text") or {})
        raise ChatError(notice or "This video has no live chat (not live, ended or chat disabled).")
    continuation, timeout = _continuation(renderer)
    if not continuation:
        raise ChatError("The live chat has ended.")
    config = {"key": key.group(1), "context": json.loads(ctx.group(1))}
    return config, parse_actions(renderer.get("actions", [])), continuation, timeout


class LiveChatClient:
    """Polls one live chat and delivers each new message once."""

    def __init__(
        self,
        url: str,
        on_message: Callable[[ChatMessage], Awaitable[None] | None],
        on_status: Callable[[ChatStatus], None] | None = None,
        skip_backlog: bool = True,
        base_url: str = BASE,
        max_backoff: float = 60.0,
    ):
        self.video_id = extract_video_id(url)
        self.on_message = on_message
        self.on_status = on_status or (lambda s: None)
        self.skip_backlog = skip_backlog
        self.base_url = base_url.rstrip("/")
        self.max_backoff = max_backoff
        self._seen: OrderedDict[str, None] = OrderedDict()
        self.received = 0
        self.failures = 0

    def _remember(self, message_id: str) -> bool:
        """True when the id is new."""
        if message_id in self._seen:
            return False
        self._seen[message_id] = None
        if len(self._seen) > 5000:
            self._seen.popitem(last=False)
        return True

    async def _deliver(self, messages: list[ChatMessage]) -> None:
        for m in messages:
            if self._remember(m.id):
                self.received += 1
                result = self.on_message(m)
                if asyncio.iscoroutine(result):
                    await result

    async def run(self) -> None:
        """Read until the chat ends or the task is cancelled; reconnects with backoff."""
        headers = {"User-Agent": _UA, "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
                   "Cookie": "SOCS=CAI; CONSENT=YES+"}
        timeout = aiohttp.ClientTimeout(total=30)
        attempt = 0
        first_connection = True
        async with aiohttp.ClientSession(headers=headers, timeout=timeout) as session:
            while True:
                try:
                    self.on_status(ChatStatus("connecting" if attempt == 0 else "reconnecting", attempt=attempt))
                    async with session.get(f"{self.base_url}/live_chat",
                                           params={"is_popout": "1", "v": self.video_id}) as resp:
                        if resp.status == 404:
                            raise ChatError("Video not found.")
                        resp.raise_for_status()
                        config, backlog, continuation, wait = parse_page(await resp.text())
                    if first_connection and self.skip_backlog:
                        for m in backlog:
                            self._remember(m.id)  # old messages: never answered
                    else:
                        await self._deliver(backlog)
                    first_connection = False
                    attempt = 0
                    self.on_status(ChatStatus("connected"))
                    await self._poll(session, config, continuation, wait)
                    self.on_status(ChatStatus("ended", "The live chat has ended."))
                    return
                except ChatError as e:
                    self.on_status(ChatStatus("error", str(e)))
                    raise
                except asyncio.CancelledError:
                    self.on_status(ChatStatus("stopped"))
                    raise
                except (aiohttp.ClientError, asyncio.TimeoutError, ValueError, KeyError) as e:
                    self.failures += 1
                    attempt += 1
                    delay = min(self.max_backoff, 2 ** min(attempt, 6))
                    log.warning("chat connection problem (%s); retry in %ss", e, delay)
                    self.on_status(ChatStatus("reconnecting", f"{type(e).__name__}: {e}", attempt))
                    await asyncio.sleep(delay)

    async def _poll(self, session: aiohttp.ClientSession, config: dict, continuation: str, wait: int) -> None:
        endpoint = f"{self.base_url}/youtubei/v1/live_chat/get_live_chat"
        while continuation:
            await asyncio.sleep(max(1.0, min(wait / 1000, 10.0)))
            body = {"context": config["context"], "continuation": continuation}
            async with session.post(endpoint, params={"key": config["key"], "prettyPrint": "false"},
                                    json=body) as resp:
                resp.raise_for_status()
                data = await resp.json(content_type=None)
            chat = (data.get("continuationContents") or {}).get("liveChatContinuation")
            if not chat:
                return  # no continuation: the stream ended
            await self._deliver(parse_actions(chat.get("actions", [])))
            continuation, wait = _continuation(chat)
