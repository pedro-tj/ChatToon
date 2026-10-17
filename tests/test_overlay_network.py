"""Overlay addresses: this computer, the local network (opt-in, same network only), roles,
a new secret address, and a busy default port (docs/ARCHITECTURE.md).

127.0.0.2 stands in for the LAN address: Linux answers the whole 127.0.0.0/8 on loopback."""

import asyncio
import socket

import aiohttp
import pytest

from chattoon.core import overlay_server
from chattoon.core.overlay_server import OverlayServer, valid_lan_address


@pytest.fixture
def web(tmp_path):
    (tmp_path / "overlay").mkdir()
    (tmp_path / "overlay" / "index.html").write_text("<html>overlay</html>")
    return tmp_path


async def get(url, host=None, local=None):
    connector = aiohttp.TCPConnector(local_addr=(local, 0)) if local else None
    async with aiohttp.ClientSession(connector=connector) as s:
        async with s.get(url, headers={"Host": host} if host else None) as r:
            return r.status, r.headers.get("Content-Security-Policy", "")


def test_only_private_ipv4_addresses_can_be_used():
    assert valid_lan_address("192.168.0.235") and valid_lan_address("10.0.0.2") and valid_lan_address("169.254.1.2")
    for bad in ("8.8.8.8", "0.0.0.0", "127.0.0.1", "::1", "fd00::1", "", "x"):
        assert not valid_lan_address(bad), bad


def test_lan_listener_answers_only_its_network(web, monkeypatch):
    monkeypatch.setattr(overlay_server, "valid_lan_address", lambda a: True)

    async def go():
        server = OverlayServer("tok123456", 0, web)
        await server.start()
        assert await server.set_lan("127.0.0.2", 8)
        lan = server.lan_url
        results = {
            "lan": await get(lan),
            "lan-wrong-host": await get(lan, host="evil.example"),
            "local": await get(server.url),
            "token": (await get(lan.replace("tok123456", "nope")))[0],
        }
        # a narrower network: 127.0.0.1 (the caller) is not in 127.0.0.2/32 anymore
        assert await server.set_lan("127.0.0.2", 32)
        results["outside"] = (await get(server.lan_url))[0]
        await server.set_lan("")
        results["off"] = server.lan_url
        try:
            await get(lan)
            results["closed"] = False
        except aiohttp.ClientError:
            results["closed"] = True
        await server.stop()
        return lan, results

    lan, r = asyncio.run(go())
    assert lan.startswith("http://127.0.0.2:") and "/o/tok123456/" in lan
    assert r["lan"][0] == 200 and "ws://127.0.0.2:" in r["lan"][1]
    assert r["lan-wrong-host"][0] == 403  # DNS rebinding through the LAN address is refused
    assert r["local"][0] == 200 and "ws://127.0.0.2" not in r["local"][1]
    assert r["token"] == 404 and r["outside"] == 403
    assert r["off"] == "" and r["closed"]  # turning it off really closes the listener


def test_lan_errors_are_reported(web):
    async def go():
        server = OverlayServer("tok123456", 0, web)
        bad = await server.set_lan("192.168.0.9")  # before start
        first = server.lan_error
        await server.start()
        public = await server.set_lan("8.8.8.8")
        second = server.lan_error
        absent = await server.set_lan("10.255.254.253")
        third = server.lan_error
        await server.stop()
        return bad, first, public, second, absent, third

    bad, first, public, second, absent, third = asyncio.run(go())
    assert not bad and first == "not-started"
    assert not public and second == "invalid-address"
    assert not absent and third == "address-unavailable"  # private, but not an address of this computer


def test_desktop_and_probe_roles(web, tmp_path):
    from .conftest import make_wav

    async def go():
        server = OverlayServer("tok123456", 0, web)
        await server.start()
        ws = f"http://127.0.0.1:{server.port}/o/tok123456/ws"
        async with aiohttp.ClientSession() as s:
            probe = await s.ws_connect(ws + "?role=probe")
            hello = await probe.receive_json(timeout=2)
            closed = (await probe.receive(timeout=2)).type
            desktop = await s.ws_connect(ws + "?role=desktop")
            obs = await s.ws_connect(ws + "?role=obs")
            await asyncio.sleep(0.1)
            counts = server.counts()
            await server.speak({"type": "speak", "id": "u1", "text": "oi"}, make_wav(tmp_path / "u.wav"), True)
            got = {}
            for name, sock in (("desktop", desktop), ("obs", obs)):
                got[name] = (await sock.receive_json(timeout=2))["audio"]
            await desktop.close()
            await obs.close()
        await server.stop()
        return hello, closed, counts, got

    hello, closed, counts, got = asyncio.run(go())
    assert hello == {"type": "hello", "ok": True} and closed == aiohttp.WSMsgType.CLOSE
    assert counts == {"obs": 1, "preview": 0, "browser": 0, "desktop": 1}  # the probe is never counted
    assert got == {"desktop": None, "obs": "audio/u1.wav"}  # the desktop window never plays the voice


def test_new_token_invalidates_every_old_address(web):
    async def go():
        server = OverlayServer("old-token-1", 0, web)
        await server.start()
        old = server.url
        await server.restart("new-token-2")
        new = server.url
        status_old, status_new = (await get(old))[0], (await get(new))[0]
        await server.stop()
        return old, new, status_old, status_new

    old, new, status_old, status_new = asyncio.run(go())
    assert "old-token-1" in old and "new-token-2" in new
    assert status_old == 404 and status_new == 200


def test_busy_default_port_moves_and_the_address_says_so(web):
    async def go():
        blocker = socket.socket()
        blocker.bind(("127.0.0.1", 0))
        blocker.listen()
        busy = blocker.getsockname()[1]
        server = OverlayServer("tok123456", busy, web)
        await server.start()
        port, url = server.port, server.url
        status = (await get(url))[0]
        await server.stop()
        blocker.close()
        return busy, port, url, status

    busy, port, url, status = asyncio.run(go())
    assert port != busy and f":{port}/" in url and status == 200


def test_engine_turns_the_lan_mode_on_and_off(web, tmp_path, monkeypatch):
    from chattoon.core import network
    from chattoon.core.config import Settings
    from chattoon.core.engine import ChatToonEngine

    from .test_engine import FakeOllama, FakePlayer, FakeTTS

    monkeypatch.setattr(overlay_server, "valid_lan_address", lambda a: True)
    monkeypatch.setattr(network, "addresses", lambda *a, **k: [network.Address("127.0.0.2", 8, "lo", "ethernet", "private")])
    events = []

    async def go():
        s = Settings()
        s.overlay.lan_enabled, s.overlay.lan_address = True, "127.0.0.2"
        engine = ChatToonEngine(s, tts=FakeTTS(tmp_path), player=FakePlayer(), ollama=FakeOllama(),
                                server=OverlayServer("tok123456", 0, web))
        engine.bus.subscribe(lambda k, d: events.append((k, d)) if k == "overlay" else None)
        await engine.startup()
        on = engine.server.lan_url
        s.overlay.lan_address = "127.0.0.9"  # the network changed: that address is gone
        await engine.apply_network()
        gone = (engine.server.lan_url, engine.server.lan_error)
        s.overlay.lan_enabled = False
        await engine.apply_network()
        off = engine.server.lan_url
        await engine.shutdown()
        return on, gone, off

    on, gone, off = asyncio.run(go())
    assert on.startswith("http://127.0.0.2:") and gone == ("", "address-unavailable") and off == ""
    assert events[-1][1]["lanUrl"] == "" and "port" in events[-1][1]
