"""Reading the viewer's name and message before the reply."""

import asyncio
import json

import pytest

from chattoon.core.config import Settings
from chattoon.core.messages import ChatMessage
from chattoon.core.reading import build_reading, cut, speakable_name, speakable_text

from .test_engine import FakeChat, FakeOllama, FakeTTS, build, kinds, wait_for


# -- text preparation -----------------------------------------------------------

@pytest.mark.parametrize("raw,spoken", [
    ("João Linux", "João Linux"),
    ("@joao_linux1987", "joao linux"),
    ("JoaoLinux", "Joao Linux"),
    ("@user-ab12cd34ef", "um espectador"),  # YouTube's generated handle
    ("😀😀😀", "um espectador"),
    ("𝓜𝓪𝓻𝓲𝓪 🐧", "Maria"),  # "fancy" Unicode letters
    ("Ana‮​", "Ana"),  # bidi/invisible characters
])
def test_speakable_names(raw, spoken):
    assert speakable_name(raw, "pt-BR") == spoken


def test_speakable_text_keeps_the_words_and_drops_what_voices_garble():
    text = speakable_text("kkkkkkkk Siiiiim!!! olha https://exemplo.com/x 😂 @Tux #linux :face-blue-smiling:", "pt-BR")
    assert text == "kkk Siiim! olha link Tux linux"


def test_reading_templates_follow_the_examples():
    joao = ChatMessage("1", "João Linux", "Bom dia pessoal! O BigLinux está voando aqui no meu computador!")
    maria = ChatMessage("2", "Maria", "Por que o Windows trava tanto?")
    assert build_reading(joao, "name_message", 180, "pt-BR").spoken == \
        "João Linux disse: Bom dia pessoal! O BigLinux está voando aqui no meu computador!"
    assert build_reading(maria, "name_message", 180, "pt-BR").spoken == "Maria perguntou: Por que o Windows trava tanto?"
    assert build_reading(maria, "name", 180, "pt-BR").spoken == "Pergunta de Maria."
    assert build_reading(joao, "name", 180, "en").spoken == "Message from João Linux."
    assert build_reading(joao, "off", 180, "pt-BR") is None
    paid = ChatMessage("3", "Bia", "valeu!", superchat="R$ 10,00")
    assert build_reading(paid, "name_message", 180, "pt-BR").spoken == "Bia mandou um Super Chat de R$ 10,00 e disse: valeu!"


def test_long_messages_are_cut_never_rewritten():
    long = "Primeira frase do espectador. " + "palavra " * 80
    r = build_reading(ChatMessage("1", "Ana", long), "name_message", 60, "pt-BR")
    assert r.text == "Primeira frase do espectador." and r.spoken == "Ana disse: Primeira frase do espectador."
    words = cut("um dois três quatro cinco seis sete oito nove dez onze doze treze", 30)
    assert words.endswith("…") and len(words) <= 31 and all(w in "um dois três quatro cinco seis" for w in words[:-1].split())


def test_emoji_or_link_only_message_reads_just_the_name():
    r = build_reading(ChatMessage("1", "Ana", "🔥🔥 https://x.com"), "name_message", 180, "pt-BR")
    assert r.mode == "name" and r.spoken == "Mensagem de Ana." and "🔗" in r.text  # bubble hides the link


# -- settings -------------------------------------------------------------------

def test_new_installations_read_name_and_message_but_old_settings_keep_direct_replies(tmp_path):
    assert Settings().reading.mode == "name_message"
    old = tmp_path / "old.json"
    old.write_text(json.dumps({"character": "tux", "mode": "auto"}))  # saved by ChatToon 2.0
    assert Settings.load(old).reading.mode == "off"
    chosen = tmp_path / "chosen.json"
    chosen.write_text(json.dumps({"reading": {"mode": "name", "max_chars": 90}}))
    loaded = Settings.load(chosen)
    assert (loaded.reading.mode, loaded.reading.max_chars) == ("name", 90)
    assert Settings.load(tmp_path / "missing.json").reading.mode == "name_message"


# -- engine flows ---------------------------------------------------------------

def speak_events(engine_events_server):
    return [e for e in engine_events_server if e.get("type") == "speak"]


def record_overlay(engine):
    sent = []
    original = engine.server.speak

    async def speak(event, wav, play_in_overlay):
        sent.append(dict(event))
        return await original(event, wav, play_in_overlay)

    engine.server.speak = speak
    return sent


def test_reads_name_and_message_then_replies_in_order(tmp_path):
    async def go():
        engine, events = build(tmp_path, reading="name_message")
        overlay = record_overlay(engine)
        await engine.start()
        engine.submit("Bom dia pessoal!", author="João Linux")
        await wait_for(lambda: engine.history)
        await engine.shutdown()
        return engine, events, overlay

    engine, events, overlay = asyncio.run(go())
    assert engine.tts.texts == ["João Linux disse: Bom dia pessoal!", "Resposta para Bom dia pessoal!!"]
    assert len(engine.player.played) == 2 and engine.player.max_active == 1  # never both at once
    assert [e["kind"] for e in overlay] == ["reading", "reply"]
    reading = overlay[0]
    assert reading["author"] == "João Linux" and reading["text"] == "Bom dia pessoal!" and reading["envelope"]
    phases = [d["phase"] for d in kinds(events, "phase")]
    assert phases.index("listening") < phases.index("reading") < phases.index("speaking")
    assert engine.history[-1]["read"] is True and engine.stats.read == 1


def test_name_only_mode(tmp_path):
    async def go():
        engine, _ = build(tmp_path, reading="name")
        overlay = record_overlay(engine)
        await engine.start()
        engine.submit("Qual distro vocês usam?", author="Carlos")
        await wait_for(lambda: engine.history)
        await engine.shutdown()
        return engine, overlay

    engine, overlay = asyncio.run(go())
    assert engine.tts.texts[0] == "Pergunta de Carlos."
    assert overlay[0]["text"] == "Qual distro vocês usam?" and overlay[0]["reveal"] is False  # bubble shows it all


def test_reading_off_replies_directly(tmp_path):
    async def go():
        engine, events = build(tmp_path, reading="off")
        await engine.start()
        engine.submit("oi", author="Ana")
        await wait_for(lambda: engine.history)
        await engine.shutdown()
        return engine, events

    engine, events = asyncio.run(go())
    assert engine.tts.texts == ["Resposta para oi!"] and engine.history[-1]["read"] is False
    assert "reading" not in [d["phase"] for d in kinds(events, "phase")]


def test_reply_is_generated_while_the_message_is_read(tmp_path):
    async def go():
        ollama = FakeOllama(delay=0.4)
        engine, _ = build(tmp_path, reading="name_message", ollama=ollama, reading__pause=0)
        engine.player.wait = lambda timeout=None: __import__("time").sleep(0.4) or True  # 0.4 s reading
        await engine.start()
        loop = asyncio.get_running_loop()
        started = loop.time()
        engine.submit("oi", author="Ana")
        await wait_for(lambda: engine.history)
        elapsed = loop.time() - started
        await engine.shutdown()
        return elapsed

    # reading (0.4 s) and generation (0.4 s) overlap; then the reply plays (0.4 s)
    assert asyncio.run(go()) < 1.4


def test_interrupt_during_reading_cancels_the_reply(tmp_path):
    async def go():
        engine, _ = build(tmp_path, reading="name_message")
        engine.player.wait = lambda timeout=None: __import__("time").sleep(0.5) or True
        await engine.start()
        engine.submit("primeira mensagem", author="Ana")
        await wait_for(lambda: engine.phase == "reading")
        await engine.interrupt()
        await asyncio.sleep(0.6)
        result = (list(engine.tts.texts), len(engine.history), engine.phase, engine.tts.cancels)
        await engine.shutdown()
        return result

    texts, history, phase, cancels = asyncio.run(go())
    assert history == 0 and phase == "idle" and cancels >= 1
    assert "Resposta para primeira mensagem!" not in texts[1:] or history == 0  # never spoken


def test_emergency_during_reading_silences_everything(tmp_path):
    async def go():
        engine, _ = build(tmp_path, reading="name_message")
        engine.player.wait = lambda timeout=None: __import__("time").sleep(0.5) or True
        await engine.start()
        engine.submit("mensagem", author="Ana")
        await wait_for(lambda: engine.phase == "reading")
        await engine.emergency_stop()
        played = len(engine.player.played)
        await asyncio.sleep(0.8)
        result = (engine.state, len(engine.player.played) == played, len(engine.history))
        await engine.shutdown()
        return result

    assert asyncio.run(go()) == ("emergency", True, 0)


def test_paused_stream_holds_the_reply_after_the_reading(tmp_path):
    async def go():
        engine, _ = build(tmp_path, reading="name_message", reading__pause=0.1)
        await engine.start()
        engine.submit("oi", author="Ana")
        await wait_for(lambda: engine.phase == "reading")
        engine.pause()
        await asyncio.sleep(0.6)
        held = (len(engine.history), list(engine.tts.texts))
        engine.resume()
        await wait_for(lambda: engine.history)
        await engine.shutdown()
        return held

    history, texts = asyncio.run(go())
    assert history == 0 and texts[0] == "Ana disse: oi."


def test_blocked_messages_are_never_read(tmp_path):
    async def go():
        engine, _ = build(tmp_path, reading="name_message", chat__blocked_words="palavrão")
        await engine.start()
        assert engine.submit("isso é um palavrão", author="Troll") == "blocked word"
        await asyncio.sleep(0.4)
        await engine.shutdown()
        return engine

    engine = asyncio.run(go())
    assert engine.tts.texts == [] and engine.player.played == []


def test_forbidden_topic_reads_only_the_name(tmp_path):
    async def go():
        engine, _ = build(tmp_path, reading="name_message", context__forbidden_topics="política partidária")
        await engine.start()
        engine.submit("vamos falar de política partidária agora", author="Ana")
        await wait_for(lambda: engine.history)
        await engine.shutdown()
        return engine

    engine = asyncio.run(go())
    assert engine.tts.texts[0] == "Mensagem de Ana."  # the off-limits words are not broadcast


def test_reading_uses_its_own_voice_when_chosen(tmp_path):
    async def go():
        engine, _ = build(tmp_path, reading="name_message", reading__voice_id="kokoro:pf_dora")
        await engine.start()
        engine.submit("oi", author="Ana")
        await wait_for(lambda: engine.history)
        await engine.shutdown()
        return engine

    engine = asyncio.run(go())
    assert engine.tts.voices_used == ["kokoro:pf_dora", "v1"]


def test_assisted_mode_reads_only_after_approval(tmp_path):
    async def go():
        engine, _ = build(tmp_path, mode="assisted", reading="name_message", chat__selection="all",
                          chat__user_cooldown=0)
        await engine.start()
        await wait_for(lambda: FakeChat.instances)
        FakeChat.instances[-1].on_message(ChatMessage("yt9", "Bia", "tux, qual distro?"))
        await wait_for(lambda: engine.suggestions)
        before = list(engine.tts.texts)
        await engine.approve("youtube-main:yt9")  # ids are namespaced by source
        await engine.shutdown()
        return engine, before

    engine, before = asyncio.run(go())
    assert before == []  # nothing is read before the streamer approves
    assert engine.tts.texts == ["Bia perguntou: tux, qual distro?", "Resposta para tux, qual distro?!"]


def test_automatic_mode_reads_youtube_messages(tmp_path):
    async def go():
        engine, _ = build(tmp_path, mode="auto", reading="name_message", chat__selection="all", chat__user_cooldown=0)
        await engine.start()
        await wait_for(lambda: FakeChat.instances)
        FakeChat.instances[-1].on_message(ChatMessage("yt10", "Carlos", "Boa noite!"))
        await wait_for(lambda: engine.history)
        await engine.shutdown()
        return engine

    assert asyncio.run(go()).tts.texts[0] == "Carlos disse: Boa noite!"


def test_tts_failure_on_reading_still_answers(tmp_path):
    class FailingReadingTTS(FakeTTS):
        def synthesize(self, text, voice, *a, **k):
            if "disse" in text:
                from chattoon.core.tts import TTSError
                raise TTSError("boom", "kokoro-failed", "boom")
            return super().synthesize(text, voice, *a, **k)

    async def go():
        engine, events = build(tmp_path, reading="name_message", tts=FailingReadingTTS(tmp_path))
        await engine.start()
        engine.submit("oi", author="Ana")
        await wait_for(lambda: engine.history)
        await engine.shutdown()
        return engine, events

    engine, events = asyncio.run(go())
    assert engine.tts.texts == ["Resposta para oi!"]  # the reply is still spoken
    err = kinds(events, "error")[0]
    assert err["source"] == "tts" and err["code"] == "kokoro-failed"


def test_switching_character_interrupts_the_sequence(tmp_path):
    async def go():
        engine, _ = build(tmp_path, reading="name_message")
        engine.player.wait = lambda timeout=None: __import__("time").sleep(0.5) or True
        await engine.start()
        engine.submit("oi", author="Ana")
        await wait_for(lambda: engine.phase == "reading")
        await engine.set_character("owl")
        await asyncio.sleep(0.7)
        result = (len(engine.history), engine.settings.character)
        await engine.shutdown()
        return result

    assert asyncio.run(go()) == (0, "owl")


def test_ollama_failure_after_reading_returns_to_idle(tmp_path):
    async def go():
        engine, events = build(tmp_path, reading="name_message", ollama=FakeOllama(fail=True))
        await engine.start()
        engine.submit("oi", author="Ana")
        await wait_for(lambda: kinds(events, "error"))
        await wait_for(lambda: engine.phase == "idle")
        await engine.shutdown()
        return engine

    engine = asyncio.run(go())
    assert engine.player.played == [] and not engine.history  # no reply: the message is not read alone


# -- Kokoro lines are voiced sentence by sentence ---------------------------------

def test_segments_only_for_slow_engines():
    from chattoon.core.engine import ChatToonEngine
    from chattoon.core.tts import Voice

    kokoro, piper = Voice("kokoro:pf_dora", "Dora", "pt-BR", "kokoro"), Voice("p", "Faber", "pt-BR", "piper")
    text = "Carlos perguntou: Boa noite! Qual distribuição Linux vocês recomendam?"
    assert ChatToonEngine.segments(text, piper) == [text]
    assert ChatToonEngine.segments(text, kokoro) == ["Carlos perguntou: Boa noite!", "Qual distribuição Linux vocês recomendam?"]
    assert ChatToonEngine.segments("Oi! Tudo bem? Sim.", kokoro) == ["Oi! Tudo bem? Sim."]  # short: one piece
    assert ChatToonEngine.segments("Ok. " + "palavra " * 12 + "fim.", kokoro)[0].startswith("Ok. palavra")  # no tiny piece


def test_kokoro_reply_plays_segment_by_segment_in_order(tmp_path):
    long_reply = "Primeira frase da resposta bem animada! Segunda frase com mais detalhes ainda. Terceira e última frase."

    class LongOllama(FakeOllama):
        async def chat(self, model, messages, **kw):
            from chattoon.core.ollama import ChatResult
            return ChatResult(json.dumps({"say": long_reply, "emotion": "happy", "intensity": 0.5}), model)

    async def go():
        engine, _ = build(tmp_path, reading="name_message", ollama=LongOllama(), ai__max_chars=400, ai__max_sentences=4)
        engine.settings.character_settings().voice_id = "kokoro:pf_dora"
        overlay = record_overlay(engine)
        await engine.start()
        engine.submit("Boa noite! Qual distribuição Linux vocês recomendam?", author="Carlos")
        await wait_for(lambda: engine.history)
        await engine.shutdown()
        return engine, overlay

    engine, overlay = asyncio.run(go())
    assert engine.tts.texts == ["Carlos perguntou: Boa noite!", "Qual distribuição Linux vocês recomendam?",
                                "Primeira frase da resposta bem animada!", "Segunda frase com mais detalhes ainda.",
                                "Terceira e última frase."]  # the reading's segments are rendered before the reply's
    assert engine.player.max_active == 1 and len(engine.player.played) == 5
    reading, reply = [e for e in overlay if e["kind"] == "reading"], [e for e in overlay if e["kind"] == "reply"]
    assert len(reading) == 2 and len(reply) == 3
    assert all(e["group"] == reply[0]["id"] for e in reply) and [e.get("continue", False) for e in reply] == [False, True, True]
    assert reply[0]["progress"][0] == 0 and reply[-1]["progress"][1] == 1 and reply[0]["text"] == long_reply
    assert engine.history[-1]["voice"] is True and engine.stats.spoken == 1


def test_interrupt_between_segments_drops_the_rest(tmp_path):
    async def go():
        engine, _ = build(tmp_path, reading="off")
        engine.settings.character_settings().voice_id = "kokoro:pf_dora"
        engine.player.wait = lambda timeout=None: __import__("time").sleep(0.4) or True
        await engine.startup()
        task = asyncio.create_task(engine.say("Primeira frase longa o bastante para dividir! Segunda frase que nunca toca."))
        await wait_for(lambda: len(engine.player.played) == 1)
        await asyncio.sleep(0.1)
        await engine.interrupt()
        await asyncio.sleep(0.6)
        task.cancel()
        result = (len(engine.player.played), engine.tts.cancels)
        await engine.shutdown()
        return result

    played, cancels = asyncio.run(go())
    assert played == 1 and cancels >= 1
