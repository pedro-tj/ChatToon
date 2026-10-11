import asyncio
import json

import aiohttp
import pytest

from chattoon.core import tts as tts_mod
from chattoon.core.overlay_server import OverlayServer
from chattoon.core.tts import AudioPlayer, BigLinuxTTS, TTSError, analyse_wav

from .conftest import make_wav


def test_analyse_wav_envelope(tmp_path):
    path = make_wav(tmp_path / "a.wav", seconds=1.0)
    duration, env = analyse_wav(path)
    assert duration == pytest.approx(1.0)
    assert len(env) == 50
    assert max(env[:10]) == 0.0 and max(env[-10:]) == 0.0  # silence = closed mouth
    assert min(env[15:35]) > 0.8  # loud middle = open mouth


def test_tts_missing_package(monkeypatch, tmp_path):
    monkeypatch.setattr(tts_mod, "TTS_BIGLINUX_DIR", tmp_path / "nope")
    t = BigLinuxTTS(tmp_path / "w")
    assert not t.available
    assert "tts-biglinux" in t.error
    with pytest.raises(TTSError):
        t.voices()


def test_text_goes_through_stdin_not_shell(monkeypatch, tmp_path):
    seen = {}

    def fake_run(cmd, input, capture_output, timeout):
        seen["cmd"], seen["input"] = cmd, input

        class R:
            returncode = 0
            stderr = b""
        return R()

    monkeypatch.setattr(tts_mod.shutil, "which", lambda name: "/usr/bin/" + name)
    monkeypatch.setattr(tts_mod.subprocess, "run", fake_run)
    evil = "'; rm -rf ~ #"
    BigLinuxTTS._run(["RHVoice-test", "-p", "x"], evil)
    assert seen["cmd"] == ["RHVoice-test", "-p", "x"] and seen["input"] == evil.encode()


def test_player_plays_one_at_a_time(monkeypatch, tmp_path):
    started = []

    class Proc:
        def __init__(self, cmd, **kw):
            self.cmd, self.alive = cmd, True
            started.append(self)

        def poll(self):
            return None if self.alive else 0

        def terminate(self):
            self.alive = False

        def wait(self, timeout=None):
            self.alive = False
            return 0

        def kill(self):
            self.alive = False

    monkeypatch.setattr(tts_mod.subprocess, "Popen", Proc)
    p = AudioPlayer()
    p.command = ["pw-play"]
    p.play(tmp_path / "1.wav")
    p.play(tmp_path / "2.wav")
    assert not started[0].alive and started[1].alive  # previous audio stopped first
    p.stop()
    assert not p.playing


@pytest.mark.live
def test_real_tts_biglinux_synthesis(tmp_path):
    t = BigLinuxTTS(tmp_path / "w")
    voice = t.suggest(("faber", "Letícia"))
    assert voice is not None
    u = t.synthesize("Olá, terráqueo! **Teste** 😂 https://x.com", voice, volume=50)
    assert u.duration > 0.5 and u.envelope and u.path.exists()
    t.shutdown()


# -- overlay server -------------------------------------------------------

async def started_server(tmp_path, **kw):
    web_dir = tmp_path / "web"
    (web_dir / "overlay").mkdir(parents=True)
    (web_dir / "overlay" / "index.html").write_text("<html>overlay</html>")
    (web_dir / "overlay" / "app.js").write_text("console.log(1)")
    server = OverlayServer("tok123", port=0, web_dir=web_dir, **kw)
    await server.start()
    return server


def test_overlay_security_and_routes(tmp_path):
    async def go():
        server = await started_server(tmp_path)
        base = f"http://127.0.0.1:{server.port}"
        async with aiohttp.ClientSession() as s:
            async with s.get(f"{base}/o/tok123/") as r:
                ok = (r.status, await r.text(), r.headers.get("Content-Security-Policy", ""))
            async with s.get(f"{base}/o/wrong/") as r:
                wrong = r.status
            async with s.get(f"{base}/o/tok123/static/overlay/app.js") as r:
                static = r.status
            async with s.get(f"{base}/o/tok123/static/../../etc/passwd") as r:
                traversal = r.status
            async with s.get(f"{base}/o/tok123/", headers={"Host": "evil.example:80"}) as r:
                rebinding = r.status
            async with s.get(f"{base}/o/tok123/audio/nothing.wav") as r:
                audio = r.status
        await server.stop()
        return ok, wrong, static, traversal, rebinding, audio, server.url

    ok, wrong, static, traversal, rebinding, audio, url = asyncio.run(go())
    assert ok[0] == 200 and "overlay" in ok[1] and "default-src 'self'" in ok[2]
    assert wrong == 404 and static == 200 and traversal in (403, 404)
    assert rebinding == 403 and audio == 404
    assert url.startswith("http://127.0.0.1:") and url.endswith("/o/tok123/")


def test_overlay_binds_loopback_only(tmp_path):
    async def go():
        server = await started_server(tmp_path)
        sockets = next(iter(server._runner.sites))._server.sockets  # type: ignore[union-attr]
        addr = sockets[0].getsockname()[0]
        await server.stop()
        return addr
    assert asyncio.run(go()) == "127.0.0.1"


def test_overlay_audio_goes_to_one_sink_and_ws_is_read_only(tmp_path):
    async def go():
        server = await started_server(tmp_path)
        ws_url = f"http://127.0.0.1:{server.port}/o/tok123/ws"
        wav = make_wav(tmp_path / "u.wav")
        async with aiohttp.ClientSession() as s:
            preview = await s.ws_connect(ws_url + "?role=preview")
            obs1 = await s.ws_connect(ws_url)
            obs2 = await s.ws_connect(ws_url)
            await asyncio.sleep(0.1)
            counts = server.counts()
            await server.broadcast({"type": "config", "character": "tux"}, keep=True)
            await obs1.send_str(json.dumps({"type": "set", "character": "worm"}))  # ignored
            await obs1.send_str("not json")
            ended = await server.speak({"type": "speak", "id": "u1", "text": "oi"}, wav, play_in_overlay=True)
            received = {}
            for name, ws in (("preview", preview), ("obs1", obs1), ("obs2", obs2)):
                while True:
                    msg = await ws.receive_json(timeout=2)
                    if msg["type"] == "speak":
                        received[name] = msg["audio"]
                        break
            async with s.get(f"http://127.0.0.1:{server.port}/o/tok123/audio/u1.wav") as r:
                audio_status = r.status
            await obs1.send_str(json.dumps({"type": "ended", "id": "u1"}))  # not the sink: ignored
            await asyncio.sleep(0.1)
            ignored = ended.is_set()
            await obs2.send_str(json.dumps({"type": "ended", "id": "u1"}))
            await asyncio.wait_for(ended.wait(), 2)
            late = await s.ws_connect(ws_url + "?role=preview")
            snapshot = await late.receive_json(timeout=2)
            for ws in (preview, obs1, obs2, late):
                await ws.close()
        await server.stop()
        return counts, received, audio_status, ignored, snapshot

    counts, received, audio_status, ignored, snapshot = asyncio.run(go())
    assert counts == {"obs": 2, "preview": 1}
    assert received == {"preview": None, "obs1": None, "obs2": "audio/u1.wav"}  # exactly one player
    assert audio_status == 200 and ignored is False
    assert snapshot == {"type": "config", "character": "tux"}  # late clients get current config
