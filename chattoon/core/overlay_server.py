"""Local web server for the OBS Browser Source overlay.

Security model:
* binds to 127.0.0.1 only; nothing is reachable from the network directly;
* every URL carries a random token (``/o/<token>/``) so other local web pages cannot
  read the avatar's events or audio;
* the Host header must be a loopback name (blocks DNS-rebinding attacks), or the one
  public host the user configured for an HTTPS reverse proxy (Caddy, nginx…) running on
  this computer — the proxy terminates TLS and forwards to 127.0.0.1;
* the WebSocket is one-way: the overlay can only say "hello" (its role) and
  "ended" (audio finished). No settings or administrative actions exist here — the
  desktop app controls the engine in-process.
"""

from __future__ import annotations

import asyncio
import json
import logging
import secrets
from pathlib import Path
from urllib.parse import urlsplit

from aiohttp import WSMsgType, web

log = logging.getLogger(__name__)

WEB_DIR = Path(__file__).resolve().parent.parent / "web"
_LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "[::1]"}


def public_base(url: str) -> str:
    """Normalise the public address typed by the user to ``https://host[:port]``.

    Only HTTPS is accepted: the overlay carries the secret token and the viewer's audio.
    A pasted overlay link keeps only its origin; credentials or another scheme yield ""."""
    url = (url or "").strip().rstrip("/")
    if not url:
        return ""
    if "://" not in url:
        url = "https://" + url
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError:
        return ""
    host = (parts.hostname or "").lower()
    if parts.scheme != "https" or not host or parts.username or parts.password:
        return ""
    if host in _LOOPBACK_HOSTS or host == "::1":
        return ""
    return f"https://{host}" + (f":{port}" if port and port != 443 else "")


class OverlayServer:
    def __init__(self, token: str, port: int = 8765, web_dir: Path = WEB_DIR, public_address: str = ""):
        self.token = token or secrets.token_urlsafe(12)
        self.set_public_address(public_address)
        self.requested_port = port
        self.port = 0
        self.web_dir = web_dir
        self._runner: web.AppRunner | None = None
        self._clients: dict[web.WebSocketResponse, str] = {}  # ws -> role
        self._audio_sink: web.WebSocketResponse | None = None
        self._audio: dict[str, Path] = {}  # utterance id -> wav
        self._ended: dict[str, asyncio.Event] = {}
        self._snapshot: dict[str, dict] = {}  # last event of each kind, replayed to new clients
        self.on_clients_changed = lambda counts: None

    # -- lifecycle --------------------------------------------------------

    async def start(self) -> None:
        app = web.Application(middlewares=[self._guard], client_max_size=64 * 1024)
        base = f"/o/{self.token}"
        app.router.add_get(base + "/", self._index)
        app.router.add_get(base + "/ws", self._ws)
        app.router.add_get(base + "/audio/{uid}.wav", self._audio_file)
        app.router.add_static(base + "/static/", self.web_dir, show_index=False, follow_symlinks=False)
        self._runner = web.AppRunner(app, access_log=None)
        await self._runner.setup()
        for port in self._ports():
            site = web.TCPSite(self._runner, "127.0.0.1", port, reuse_address=True)
            try:
                await site.start()
            except OSError:
                continue
            self.port = site._server.sockets[0].getsockname()[1]  # type: ignore[union-attr]
            log.info("overlay at %s", self.url)
            return
        raise OSError("No free local port for the overlay server")

    def _ports(self):
        if self.requested_port:
            yield from range(self.requested_port, self.requested_port + 10)
        yield 0  # any free port

    async def stop(self) -> None:
        for ws in list(self._clients):
            await ws.close()
        if self._runner:
            await self._runner.cleanup()
            self._runner = None

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}/o/{self.token}/"

    @property
    def public_url(self) -> str:
        """The overlay through the user's HTTPS reverse proxy, or "" when not configured."""
        return f"{self._public_base}/o/{self.token}/" if self._public_base else ""

    def set_public_address(self, url: str) -> None:
        """Accept requests for this HTTPS address (e.g. ``https://example.org:8443``)."""
        self._public_base = public_base(url)
        self._public_host = urlsplit(self._public_base).hostname or ""

    def counts(self) -> dict[str, int]:
        out = {"obs": 0, "preview": 0}
        for role in self._clients.values():
            out[role] = out.get(role, 0) + 1
        return out

    # -- http -------------------------------------------------------------

    @web.middleware
    async def _guard(self, request: web.Request, handler):
        host = request.host or ""
        host = host[: host.index("]") + 1] if host.startswith("[") and "]" in host else host.split(":")[0]
        if host.lower() not in _LOOPBACK_HOSTS and not (self._public_host and host.lower() == self._public_host):
            return web.Response(status=403, text="forbidden")
        response = await handler(request)
        if isinstance(response, web.StreamResponse) and not isinstance(response, web.WebSocketResponse):
            response.headers.setdefault("Cache-Control", "no-store")
            response.headers.setdefault("X-Content-Type-Options", "nosniff")
            response.headers.setdefault("Referrer-Policy", "no-referrer")
        return response

    async def _index(self, request: web.Request) -> web.StreamResponse:
        html = (self.web_dir / "overlay" / "index.html").read_text(encoding="utf-8")
        resp = web.Response(text=html, content_type="text/html")
        sockets = "ws://127.0.0.1:* ws://localhost:*"
        if self._public_host and request.host.split(":")[0].lower() == self._public_host:
            sockets += " " + self._public_base.replace("https://", "wss://", 1)  # served through the proxy
        resp.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
            f"connect-src 'self' {sockets}; media-src 'self'; img-src 'self' data:"
        )
        return resp

    async def _audio_file(self, request: web.Request) -> web.StreamResponse:
        path = self._audio.get(request.match_info["uid"])
        if not path or not path.exists():
            raise web.HTTPNotFound()
        return web.FileResponse(path, headers={"Content-Type": "audio/wav"})

    # -- websocket --------------------------------------------------------

    async def _ws(self, request: web.Request) -> web.WebSocketResponse:
        ws = web.WebSocketResponse(heartbeat=20, max_msg_size=4096)
        await ws.prepare(request)
        role = "preview" if request.query.get("role") == "preview" else "obs"
        self._clients[ws] = role
        if role == "obs":
            self._audio_sink = ws  # the newest OBS source plays audio; others stay silent
        self.on_clients_changed(self.counts())
        try:
            for event in self._snapshot.values():
                await ws.send_json(event)
            async for msg in ws:
                if msg.type != WSMsgType.TEXT:
                    continue
                try:
                    data = json.loads(msg.data)
                except ValueError:
                    continue
                if isinstance(data, dict) and data.get("type") == "ended" and ws is self._audio_sink:
                    event = self._ended.get(str(data.get("id", "")))
                    if event:
                        event.set()
                # anything else is ignored on purpose: the overlay has no authority
        finally:
            self._clients.pop(ws, None)
            if self._audio_sink is ws:
                self._audio_sink = next((w for w, r in reversed(list(self._clients.items())) if r == "obs"), None)
            self.on_clients_changed(self.counts())
        return ws

    async def broadcast(self, event: dict, keep: bool = False) -> None:
        if keep:
            self._snapshot[event["type"]] = event
        dead = []
        for ws in list(self._clients):
            try:
                await ws.send_json(event)
            except (ConnectionResetError, RuntimeError):
                dead.append(ws)
        for ws in dead:
            self._clients.pop(ws, None)

    @property
    def has_audio_sink(self) -> bool:
        return self._audio_sink is not None and not self._audio_sink.closed

    async def speak(self, event: dict, wav: Path | None, play_in_overlay: bool) -> asyncio.Event | None:
        """Send a speak event. With ``play_in_overlay`` only the audio sink gets the audio URL,
        so a reply is heard exactly once even with several overlays open."""
        uid = event["id"]
        ended = None
        if play_in_overlay and wav is not None and self.has_audio_sink:
            self._audio = {uid: wav}  # only the current utterance is downloadable
            ended = self._ended.setdefault(uid, asyncio.Event())
        sink = self._audio_sink if ended else None
        for ws in list(self._clients):
            payload = dict(event, audio=f"audio/{uid}.wav" if ws is sink else None)
            try:
                await ws.send_json(payload)
            except (ConnectionResetError, RuntimeError):
                self._clients.pop(ws, None)
        return ended

    def forget_utterance(self, uid: str) -> None:
        self._ended.pop(uid, None)

