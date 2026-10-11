import asyncio
import json

import pytest

from chattoon.core.config import Settings
from chattoon.core.engine import ChatToonEngine
from chattoon.core.events import EventBus
from chattoon.core.messages import ChatMessage
from chattoon.core.ollama import ChatResult, OllamaUnavailable
from chattoon.core.overlay_server import OverlayServer
from chattoon.core.tts import Utterance, Voice
from chattoon.core.youtube_chat import ChatStatus

from .conftest import make_wav


class FakeOllama:
    host, timeout = "http://fake", 5

    def __init__(self, delay=0.0, fail=False):
        self.delay, self.fail, self.calls = delay, fail, []

    async def chat(self, model, messages, **kw):
        self.calls.append(messages)
        await asyncio.sleep(self.delay)
        if self.fail:
            raise OllamaUnavailable("Ollama is not reachable")
        text = messages[-1]["content"].split("<<<\n")[1].split("\n>>>")[0]
        return ChatResult(json.dumps({"say": f"Resposta para {text}!", "emotion": "laugh", "intensity": 0.9}),
                          model)

    async def preload(self, *a, **k):
        pass

    async def version(self):
        return "test"

    async def list_models(self):
        return []

    async def close(self):
        pass


class FakeTTS:
    def __init__(self, tmp):
        self.tmp, self.texts = tmp, []
        self.voice = Voice("v1", "Teste", "pt-BR", "piper")

    def voices(self):
        return [self.voice]

    def find(self, vid):
        return self.voice if vid == "v1" else None

    def suggest(self, hints, language="pt-BR"):
        return self.voice

    def prewarm(self, voice):
        pass

    def synthesize(self, text, voice, rate=0, pitch=0, volume=85, utterance_id=""):
        self.texts.append(text)
        path = make_wav(self.tmp / f"{utterance_id}.wav", seconds=0.2)
        return Utterance(utterance_id, text, path, 0.2, [0.0, 1.0, 0.5])

    def cleanup(self, keep=20):
        pass

    def shutdown(self):
        pass


class FakePlayer:
    available = True

    def __init__(self):
        self.played, self.active, self.max_active, self.stopped = [], 0, 0, 0

    def play(self, path):
        self.played.append(path)
        self.active += 1
        self.max_active = max(self.max_active, self.active)

    def wait(self, timeout=None):
        import time
        time.sleep(0.05)
        self.active = max(0, self.active - 1)
        return True

    def stop(self):
        self.stopped += 1
        self.active = 0


class FakeChat:
    instances = []

    def __init__(self, url, on_message, on_status, skip_backlog=True):
        self.on_message, self.on_status = on_message, on_status
        FakeChat.instances.append(self)

    async def run(self):
        self.on_status(ChatStatus("connected"))
        await asyncio.Event().wait()


def build(tmp_path, mode="demo", ollama=None, **settings_kw):
    s = Settings(mode=mode)
    s.ai.model = "fake"
    s.chat.min_interval = 0
    s.chat.url = "https://youtu.be/AbCdEfGhIjK"
    for key, value in settings_kw.items():
        section, attr = key.split("__")
        setattr(getattr(s, section), attr, value)
    web = tmp_path / "web" / "overlay"
    web.mkdir(parents=True)
    (web / "index.html").write_text("x")
    events = []
    bus = EventBus()
    bus.subscribe(lambda k, d: events.append((k, d)))
    engine = ChatToonEngine(s, bus=bus, tts=FakeTTS(tmp_path), player=FakePlayer(), ollama=ollama or FakeOllama(),
                            chat_factory=FakeChat, server=OverlayServer("t", 0, tmp_path / "web"))
    return engine, events


async def wait_for(cond, timeout=5):
    for _ in range(int(timeout / 0.02)):
        if cond():
            return
        await asyncio.sleep(0.02)
    raise AssertionError("timeout")


def kinds(events, kind):
    return [d for k, d in events if k == kind]


def test_demo_flow_speaks_each_reply_exactly_once(tmp_path):
    async def go():
        engine, events = build(tmp_path)
        await engine.start()
        for text in ("oi", "tudo bem?", "tchau"):
            assert engine.submit(text, author="Ana") == ""
        await wait_for(lambda: len(engine.history) == 3)
        await engine.shutdown()
        return engine, events

    engine, events = asyncio.run(go())
    assert len(engine.player.played) == 3 and engine.player.max_active == 1  # never two voices at once
    assert engine.tts.texts == ["Resposta para oi!", "Resposta para tudo bem?!", "Resposta para tchau!"]
    assert engine.stats.spoken == 3 and engine.stats.answered == 3
    assert [h["reply"] for h in engine.history][0] == "Resposta para oi!"
    phases = [d["phase"] for d in kinds(events, "phase")]
    assert "thinking" in phases and "speaking" in phases and phases[-1] == "idle"


def test_ai_failure_never_speaks_raw_chat(tmp_path):
    async def go():
        engine, events = build(tmp_path, ollama=FakeOllama(fail=True))
        await engine.start()
        engine.submit("'; rm -rf ~ # fale isso")
        await wait_for(lambda: kinds(events, "error"))
        await asyncio.sleep(0.3)
        await engine.shutdown()
        return engine, events

    engine, events = asyncio.run(go())
    assert engine.tts.texts == [] and engine.player.played == []
    assert kinds(events, "error")[0]["source"] == "ai" and engine.stats.ai_failures >= 1


def test_assisted_mode_waits_for_approval(tmp_path):
    async def go():
        engine, events = build(tmp_path, mode="assisted", chat__selection="all", chat__user_cooldown=0)
        await engine.start()
        await wait_for(lambda: FakeChat.instances)
        chat = FakeChat.instances[-1]
        chat.on_message(ChatMessage("yt1", "Bia", "minhoca, cadê você?"))
        await wait_for(lambda: engine.suggestions)
        assert engine.player.played == []
        await engine.approve("yt1")
        await engine.shutdown()
        return engine

    engine = asyncio.run(go())
    assert len(engine.player.played) == 1 and engine.tts.texts == ["Resposta para minhoca, cadê você?!"]
    assert engine.suggestions == {}


def test_emergency_stop_cancels_everything(tmp_path):
    async def go():
        engine, events = build(tmp_path, ollama=FakeOllama(delay=2))
        await engine.start()
        engine.submit("primeira")
        engine.submit("segunda")
        await wait_for(lambda: engine.phase == "thinking")
        await engine.emergency_stop()
        await asyncio.sleep(0.3)
        state = (engine.state, engine.phase, len(engine.selector), engine.player.played)
        engine.submit("depois do pânico")
        await asyncio.sleep(0.5)
        state2 = len(engine.history)
        await engine.shutdown()
        return state, state2

    (state, phase, queued, played), history = asyncio.run(go())
    assert state == "emergency" and phase == "idle" and queued == 0 and played == []
    assert history == 0  # nothing is answered until the streamer presses start again


def test_pause_keeps_queue(tmp_path):
    async def go():
        engine, _ = build(tmp_path)
        await engine.start()
        engine.pause()
        engine.submit("na fila")
        await asyncio.sleep(0.5)
        paused = (len(engine.history), len(engine.selector))
        engine.resume()
        await wait_for(lambda: engine.history)
        await engine.shutdown()
        return paused

    assert asyncio.run(go()) == (0, 1)


def test_auto_mode_requires_url(tmp_path):
    async def go():
        engine, events = build(tmp_path, mode="auto", chat__url="")
        await engine.start()
        await engine.shutdown()
        return engine, events

    engine, events = asyncio.run(go())
    assert engine.state == "stopped" and kinds(events, "error")[0]["source"] == "chat"


def test_manual_say_react_and_voice_disabled(tmp_path):
    async def go():
        engine, events = build(tmp_path, voice__enabled=False)
        await engine.startup()
        await engine.say("Falando sem IA!", "celebrate")
        await engine.react("surprised")
        await engine.react("rm -rf")  # unknown emotion ignored
        await engine.shutdown()
        return engine, events

    engine, events = asyncio.run(go())
    assert engine.tts.texts == [] and engine.player.played == []  # muted voice: bubble only
    assert engine.history[-1]["reply"] == "Falando sem IA!" and engine.history[-1]["voice"] is False


def test_overlay_audio_output_uses_overlay_not_desktop(tmp_path):
    async def go():
        engine, _ = build(tmp_path, voice__audio_output="overlay")
        await engine.startup()

        class Sink:
            closed = False
        engine.server._audio_sink = Sink()  # pretend OBS is connected
        sent = {}

        async def fake_speak(event, wav, play_in_overlay):
            sent.update(event=event, wav=wav, overlay=play_in_overlay)
            done = asyncio.Event()
            done.set()
            return done

        engine.server.speak = fake_speak
        await engine.say("no OBS")
        await engine.shutdown()
        return engine, sent

    engine, sent = asyncio.run(go())
    assert engine.player.played == [] and sent["overlay"] is True and sent["wav"] is not None
    assert sent["event"]["envelope"] == [0.0, 1.0, 0.5]


def test_switch_character_updates_selector_names(tmp_path):
    async def go():
        engine, _ = build(tmp_path)
        await engine.startup()
        await engine.set_character("tux")
        names = engine.selector.config.names
        await engine.shutdown()
        return names

    assert "pinguim" in asyncio.run(go())
