"""Drive a headless Chrome/Chromium through the DevTools protocol (development only).

Used by tools/render_thumbnails.py and the browser tests. The overlay page is opened in
"capture" mode (?capture=1), where window.chattoonCapture steps the animation by exact
amounts, so screenshots and checks are deterministic. Nothing here is needed to run
ChatToon.
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import os
import shutil
import socket
import subprocess
import tempfile

import aiohttp

BROWSERS = ("chromium", "chromium-browser", "google-chrome-stable", "google-chrome", "/opt/google/chrome/chrome",
            "brave", "brave-browser")


def find_browser() -> str | None:
    env = os.environ.get("CHATTOON_BROWSER")
    if env:
        return env if shutil.which(env) or os.path.isfile(env) else None
    for name in BROWSERS:
        path = shutil.which(name) or (name if os.path.isfile(name) else None)
        if path and not _is_wrapper_script(path):
            return path
    return None


def _is_wrapper_script(path: str) -> bool:
    """Some distributions ship shell launchers that ignore --headless flags."""
    try:
        with open(os.path.realpath(path), "rb") as f:
            return f.read(2) == b"#!"
    except OSError:
        return True


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Page:
    """One browser tab: navigate, evaluate JavaScript, take screenshots."""

    def __init__(self, ws: aiohttp.ClientWebSocketResponse):
        self.ws = ws
        self._id = 0
        self.errors: list[str] = []  # JavaScript exceptions and console errors

    async def call(self, method: str, **params):
        self._id += 1
        my = self._id
        await self.ws.send_json({"id": my, "method": method, "params": params})
        while True:
            msg = await self.ws.receive_json()
            if msg.get("method") == "Runtime.exceptionThrown":
                d = msg["params"]["exceptionDetails"]
                self.errors.append(d.get("exception", {}).get("description") or d.get("text", "exception"))
            elif msg.get("method") == "Runtime.consoleAPICalled" and msg["params"]["type"] == "error":
                self.errors.append(" ".join(str(a.get("value", a.get("description", ""))) for a in msg["params"]["args"]))
            if msg.get("id") == my:
                if "error" in msg:
                    raise RuntimeError(msg["error"].get("message", str(msg["error"])))
                return msg.get("result", {})

    async def eval(self, expression: str):
        result = await self.call("Runtime.evaluate", expression=expression, returnByValue=True, awaitPromise=True)
        if "exceptionDetails" in result:
            raise RuntimeError(result["exceptionDetails"].get("exception", {}).get("description", "evaluation failed"))
        return result.get("result", {}).get("value")

    async def open(self, url: str, width: int = 640, height: int = 720, transparent: bool = False,
                   ready: str = "!!(window.chattoonCapture && window.chattoonCapture.character())") -> None:
        await self.call("Emulation.setDeviceMetricsOverride", width=width, height=height, deviceScaleFactor=1, mobile=False)
        if transparent:
            await self.call("Emulation.setDefaultBackgroundColorOverride", color={"r": 0, "g": 0, "b": 0, "a": 0})
        await self.call("Page.navigate", url=url)
        for _ in range(150):
            with contextlib.suppress(RuntimeError):
                if await self.eval(ready):
                    return
            await asyncio.sleep(0.1)
        raise RuntimeError(f"page not ready: {url} {self.errors}")

    async def screenshot(self) -> bytes:
        await asyncio.sleep(0.05)
        shot = await self.call("Page.captureScreenshot", format="png")
        return base64.b64decode(shot["data"])


@contextlib.asynccontextmanager
async def browser(path: str | None = None):
    """Start a headless browser with software WebGL and yield a Page."""
    path = path or find_browser()
    if not path:
        raise FileNotFoundError("no Chrome/Chromium found (set CHATTOON_BROWSER)")
    port = _free_port()
    profile = tempfile.mkdtemp(prefix="chattoon-headless-")
    proc = subprocess.Popen(
        [path, "--headless=new", "--no-sandbox", "--use-angle=swiftshader", "--enable-unsafe-swiftshader",
         "--hide-scrollbars", "--mute-audio", "--autoplay-policy=no-user-gesture-required",  # as OBS does
         f"--remote-debugging-port={port}", f"--user-data-dir={profile}",
         "about:blank"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        async with aiohttp.ClientSession() as session:
            targets = None
            for _ in range(100):
                try:
                    async with session.get(f"http://127.0.0.1:{port}/json") as r:
                        targets = await r.json()
                        break
                except aiohttp.ClientError:
                    await asyncio.sleep(0.1)
            if not targets:
                raise RuntimeError("the browser did not start")
            target = next(t for t in targets if t["type"] == "page")
            async with session.ws_connect(target["webSocketDebuggerUrl"], max_msg_size=0) as ws:
                page = Page(ws)
                await page.call("Runtime.enable")
                yield page
    finally:
        proc.terminate()
        try:
            proc.wait(5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
        shutil.rmtree(profile, ignore_errors=True)
