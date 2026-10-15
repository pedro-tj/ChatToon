"""YouTube Live: the ChatToon 2.x reader (public pop-out chat, no login) as a connector.

The source may be a video/live URL (read until that live ends, exactly like before) or a
channel (``@handle``, ``/channel/UC…``): then the channel's ``/live`` page tells which
video is live now, and the source waits for the next broadcast when it ends.
"""

from __future__ import annotations

import re

import aiohttp

from ..youtube_chat import _UA, BASE, ChatError, ChatStatus, LiveChatClient, extract_video_id
from .base import Connector, FatalError, NotLive, ProbeResult, StreamMetadata, TransientError

_CANONICAL = re.compile(r'<link rel="canonical" href="https://www\.youtube\.com/watch\?v=([A-Za-z0-9_-]{11})"')


class YouTubeConnector(Connector):
    platform = "youtube"
    label = "YouTube"
    support = "functional"

    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)
        target = self.source.target.strip()
        self.channel_url = target if re.search(r"/(@[^/]+|channel/[^/]+|c/[^/]+|user/[^/]+)/live$", target) else ""
        self.reconnect_when_ended = bool(self.channel_url)
        self.base_url = self.ctx.extra.get("youtube_base", BASE)
        self.client_factory = self.ctx.extra.get("youtube_client", LiveChatClient)
        self.video_id = ""
        self._client = None
        if not self.channel_url:
            self.video_id = extract_video_id(target)  # ValueError -> the manager reports a bad URL
            self._client = self._make_client(self.video_id)  # created at once, like ChatToon 2.x

    def _make_client(self, video: str):
        return self.client_factory(f"https://www.youtube.com/watch?v={video}", self.emit, self._chat_status,
                                   skip_backlog=self.ctx.skip_backlog)

    async def resolve_live(self) -> str:
        """Video id currently live on the channel (NotLive when there is none)."""
        path = self.channel_url.removeprefix("https://www.youtube.com")
        headers = {"User-Agent": _UA, "Accept-Language": "en", "Cookie": "SOCS=CAI; CONSENT=YES+"}
        async with aiohttp.ClientSession(headers=headers, timeout=aiohttp.ClientTimeout(total=20)) as session:
            async with session.get(self.base_url + path) as resp:
                if resp.status == 404:
                    raise FatalError("Channel not found.", "not-found")
                if resp.status >= 500 or resp.status == 429:
                    raise TransientError(f"HTTP {resp.status}")
                html = await resp.text()
        match = _CANONICAL.search(html)
        if not match:
            raise NotLive("The channel is not live right now.")
        return match.group(1)

    async def session(self) -> None:
        client, self._client = self._client, None
        if client is None:
            client = self._make_client(await self.resolve_live() if self.channel_url else self.video_id)
        try:
            await client.run()
        except ChatError as e:
            text = str(e)
            if self.channel_url:
                raise NotLive(text) from None
            raise FatalError(text, "ended" if "ended" in text else "chat-unavailable") from None

    def _chat_status(self, status: ChatStatus) -> None:
        if status.state == "connected":
            handle = re.search(r"/(@[^/]+)/live$", self.channel_url)
            self.connected(handle.group(1) if handle else f"video {self.video_id}" if self.video_id else "")
        elif status.state == "reconnecting":
            self.status.attempt = status.attempt
            self.set_status("reconnecting", "network", status.detail)

    async def metadata(self) -> StreamMetadata:
        """Title and channel of the live through YouTube's official oEmbed endpoint (no key,
        no login). Description and tags would need the YouTube Data API: not provided."""
        md = StreamMetadata(self.source.id, "youtube", method="YouTube oEmbed (official)")
        handle = re.search(r"/(@[^/]+)/live$", self.channel_url)
        md.channel = handle.group(1) if handle else ""
        md.url = self.channel_url.removesuffix("/live") if self.channel_url else ""
        try:
            video = await self.resolve_live() if self.channel_url else self.video_id
        except NotLive:
            md.live, md.code = False, "offline"
            md.detail = "The channel is not live right now: only its handle is known."
            return md
        url = f"https://www.youtube.com/watch?v={video}"
        async with aiohttp.ClientSession(headers={"User-Agent": _UA}, timeout=aiohttp.ClientTimeout(total=15)) as http:
            async with http.get(f"{self.base_url}/oembed", params={"url": url, "format": "json"}) as resp:
                if resp.status in (401, 403, 404):
                    return StreamMetadata(self.source.id, "youtube", ok=False, code="not-found", method=md.method,
                                          detail="YouTube has no public information about this video.")
                if resp.status >= 400:
                    raise TransientError(f"oEmbed: HTTP {resp.status}")
                data = await resp.json(content_type=None)
        md.title = str(data.get("title") or "")
        md.channel = str(data.get("author_name") or md.channel)
        md.url = str(data.get("author_url") or md.url)
        md.live = True if self.channel_url else None
        md.detail = "Description and tags need the YouTube Data API, which ChatToon does not use."
        return md

    async def probe(self) -> ProbeResult:
        try:
            video = await self.resolve_live() if self.channel_url else self.video_id
        except NotLive:
            return ProbeResult(True, "offline")  # the channel exists; it is just not live now
        except FatalError as e:
            return ProbeResult(False, e.code, str(e))
        except (aiohttp.ClientError, OSError, TimeoutError, TransientError) as e:
            return ProbeResult(False, "network", type(e).__name__)
        headers = {"User-Agent": _UA, "Cookie": "SOCS=CAI; CONSENT=YES+"}
        try:
            async with aiohttp.ClientSession(headers=headers, timeout=aiohttp.ClientTimeout(total=20)) as session:
                async with session.get(f"{self.base_url}/live_chat", params={"is_popout": "1", "v": video}) as resp:
                    html = await resp.text()
        except (aiohttp.ClientError, OSError, TimeoutError) as e:
            return ProbeResult(False, "network", type(e).__name__)
        if '"liveChatRenderer"' in html:
            return ProbeResult(True, "live", channel=video)
        return ProbeResult(False, "chat-unavailable", "This video has no live chat (not live, ended or chat disabled).")
