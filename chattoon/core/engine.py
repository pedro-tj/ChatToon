"""Application controller: chat → selection → AI → validation → voice → animation → history."""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from collections import deque
from dataclasses import dataclass, field

from .brain import REPLY_SCHEMA, Brain, Reply
from .characters import EMOTIONS, Character, get_character
from .config import Settings
from .events import EventBus
from .messages import ChatMessage, MessageSelector, SelectorConfig, clean_text
from .ollama import OllamaClient, OllamaError
from .overlay_server import OverlayServer
from .tts import AudioPlayer, BigLinuxTTS, TTSError, Voice
from .youtube_chat import ChatError, ChatStatus, LiveChatClient

log = logging.getLogger(__name__)

STATES = ("stopped", "running", "paused", "emergency")
PHASES = ("idle", "thinking", "speaking")


@dataclass
class Stats:
    received: int = 0
    dropped: int = 0
    answered: int = 0
    spoken: int = 0
    ai_failures: int = 0
    tts_failures: int = 0
    chat_failures: int = 0
    generation: deque = field(default_factory=lambda: deque(maxlen=50))
    synthesis: deque = field(default_factory=lambda: deque(maxlen=50))
    speech: deque = field(default_factory=lambda: deque(maxlen=50))

    def to_dict(self) -> dict:
        def avg(values):
            return round(sum(values) / len(values), 2) if values else 0.0

        return {
            "received": self.received, "dropped": self.dropped, "answered": self.answered,
            "spoken": self.spoken, "ai_failures": self.ai_failures, "tts_failures": self.tts_failures,
            "chat_failures": self.chat_failures, "avg_generation": avg(self.generation),
            "avg_synthesis": avg(self.synthesis), "avg_speech": avg(self.speech),
        }


class ChatToonEngine:
    def __init__(
        self,
        settings: Settings,
        bus: EventBus | None = None,
        tts: BigLinuxTTS | None = None,
        player: AudioPlayer | None = None,
        ollama: OllamaClient | None = None,
        chat_factory=LiveChatClient,
        server: OverlayServer | None = None,
    ):
        self.settings = settings
        self.bus = bus or EventBus()
        self.tts = tts or BigLinuxTTS()
        self.player = player or AudioPlayer()
        self.ollama = ollama or OllamaClient(settings.ai.host, settings.ai.timeout)
        self.chat_factory = chat_factory
        self.server = server or OverlayServer(settings.overlay.token, settings.overlay.port)
        self.server.on_clients_changed = lambda counts: self.bus.emit("overlay_clients", counts)
        self.brain = Brain()
        self.selector = MessageSelector(self._selector_config())
        self.stats = Stats()
        self.history: deque[dict] = deque(maxlen=300)
        self.suggestions: dict[str, Reply] = {}
        self.state = "stopped"
        self.phase = "idle"
        self.chat_status = ChatStatus("stopped")
        self._worker: asyncio.Task | None = None
        self._chat_task: asyncio.Task | None = None
        self._current: asyncio.Task | None = None
        self._speech_lock = asyncio.Lock()
        self._last_speech_end = 0.0
        self._started = False

    # -- setup ------------------------------------------------------------

    @property
    def character(self) -> Character:
        return get_character(self.settings.character)

    def _selector_config(self) -> SelectorConfig:
        c = self.settings.chat
        mode = "all" if self.settings.mode == "demo" else c.selection
        return SelectorConfig(
            mode=mode, user_cooldown=0 if self.settings.mode == "demo" else c.user_cooldown,
            max_queue=c.max_queue, ttl=c.message_ttl, max_chars=c.max_message_chars,
            ignore_commands=c.ignore_commands,
            blocked_words=tuple(w.strip() for w in c.blocked_words.split(",") if w.strip()),
            superchat_priority=c.superchat_priority,
            names=(self.character.name, *self.character.aliases),
        )

    def apply_settings(self) -> None:
        """Call after the settings object changed."""
        self.selector.config = self._selector_config()
        self.ollama.host = self.settings.ai.host.rstrip("/")
        self.ollama.timeout = self.settings.ai.timeout
        self._emit_overlay_config()

    async def startup(self) -> None:
        """Start the overlay server and the worker; the avatar is idle until start()."""
        if self._started:
            return
        await self.server.start()
        self._started = True
        self._worker = asyncio.create_task(self._work(), name="chattoon-worker")
        self.bus.emit("overlay", {"url": self.server.url})
        self._emit_overlay_config()
        await self.server.broadcast({"type": "state", "phase": "idle", "state": self.state}, keep=True)

    async def shutdown(self) -> None:
        await self.stop()
        if self._worker:
            self._worker.cancel()
        await self.server.stop()
        await self.ollama.close()
        self.tts.shutdown()

    # -- diagnostics ------------------------------------------------------

    async def check_services(self) -> dict:
        report: dict = {"ollama": {}, "tts": {}, "player": self.player.available}
        try:
            version = await self.ollama.version()
            models = await self.ollama.list_models()
            report["ollama"] = {"ok": True, "version": version, "models": [m.name for m in models],
                                "details": [{"name": m.name, "size": m.size_gb, "parameters": m.parameters}
                                            for m in models]}
        except OllamaError as e:
            report["ollama"] = {"ok": False, "error": str(e), "models": []}
        try:
            voices = await asyncio.to_thread(self.tts.voices)
            report["tts"] = {"ok": True, "voices": [v.__dict__ for v in voices]}
        except TTSError as e:
            report["tts"] = {"ok": False, "error": str(e), "voices": []}
        self.bus.emit("services", report)
        return report

    def voice_for(self, character: Character | None = None) -> Voice | None:
        character = character or self.character
        cs = self.settings.character_settings(character.id)
        try:
            return (self.tts.find(cs.voice_id) if cs.voice_id else None) or \
                self.tts.suggest(character.voice_hints, self.settings.ai.reply_language)
        except TTSError:
            return None

    async def warm_up(self) -> None:
        """Load the model and the voice so the first reply is fast."""
        voice = self.voice_for()
        if voice:
            try:
                await asyncio.to_thread(self.tts.prewarm, voice)
            except TTSError:
                pass
        if self.settings.ai.model:
            try:
                await self.ollama.preload(self.settings.ai.model, self.settings.ai.keep_alive)
            except OllamaError as e:
                self._error("ai", str(e))

    # -- state machine ----------------------------------------------------

    def _set_state(self, state: str) -> None:
        self.state = state
        self.bus.emit("state", {"state": state, "mode": self.settings.mode})
        asyncio.ensure_future(self.server.broadcast({"type": "state", "state": state, "phase": self.phase},
                                                    keep=True))

    def _set_phase(self, phase: str, **extra) -> None:
        self.phase = phase
        self.bus.emit("phase", {"phase": phase, **extra})
        asyncio.ensure_future(self.server.broadcast({"type": "state", "state": self.state, "phase": phase,
                                                     **extra}, keep=True))

    async def start(self) -> None:
        await self.startup()
        self.apply_settings()
        if self.settings.mode != "demo" and not self.settings.chat.url.strip():
            self._error("chat", "Paste the YouTube live URL before starting.")
            return
        self._set_state("running")
        if self.settings.mode != "demo":
            self._start_chat()
        asyncio.create_task(self.warm_up())

    def pause(self) -> None:
        if self.state == "running":
            self._set_state("paused")

    def resume(self) -> None:
        if self.state == "paused":
            self._set_state("running")

    async def stop(self) -> None:
        await self._stop_chat()
        await self.interrupt()
        self.suggestions.clear()
        self._emit_queue()
        if self.state != "emergency":
            self._set_state("stopped")

    async def emergency_stop(self) -> None:
        """Panic button: nothing more is read, generated or spoken until start()."""
        self._set_state("emergency")
        await self._stop_chat()
        self.selector.clear()
        self.suggestions.clear()
        await self.interrupt()
        await self.server.broadcast({"type": "stop"})
        self._emit_queue()

    async def interrupt(self) -> None:
        """Cancel the current generation/speech (the queue is kept)."""
        task, self._current = self._current, None
        self.player.stop()
        if task and not task.done():
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
        await self.server.broadcast({"type": "stop"})
        self._set_phase("idle")

    def clear_queue(self) -> None:
        self.selector.clear()
        self._emit_queue()

    # -- chat -------------------------------------------------------------

    def _start_chat(self) -> None:
        if self._chat_task and not self._chat_task.done():
            return
        try:
            client = self.chat_factory(self.settings.chat.url, self._on_chat_message, self._on_chat_status,
                                       skip_backlog=self.settings.chat.skip_backlog)
        except ValueError as e:
            self._error("chat", str(e))
            return
        self._chat_task = asyncio.create_task(self._run_chat(client), name="chattoon-chat")

    async def _run_chat(self, client) -> None:
        try:
            await client.run()
        except ChatError:
            pass  # status already reported
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001
            self._error("chat", str(e))

    async def _stop_chat(self) -> None:
        task, self._chat_task = self._chat_task, None
        if task and not task.done():
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass

    def _on_chat_status(self, status: ChatStatus) -> None:
        self.chat_status = status
        if status.state == "reconnecting" and status.attempt:
            self.stats.chat_failures += 1
        self.bus.emit("chat_status", {"state": status.state, "detail": status.detail, "attempt": status.attempt})

    def _on_chat_message(self, msg: ChatMessage) -> None:
        self.stats.received += 1
        reason = self.selector.offer(msg) if self.state in ("running", "paused") else "not running"
        if reason:
            self.stats.dropped += 1
        self.bus.emit("message", dict(msg.to_dict(), dropped=reason))
        self._emit_queue()

    def submit(self, text: str, author: str = "You", platform: str = "demo") -> str:
        """Demo/manual message typed by the streamer."""
        msg = ChatMessage(id=f"{platform}-{uuid.uuid4().hex[:10]}", author=author, text=text,
                          platform=platform)
        self.stats.received += 1
        reason = self.selector.offer(msg)
        if reason:
            self.stats.dropped += 1
        self.bus.emit("message", dict(msg.to_dict(), dropped=reason))
        self._emit_queue()
        return reason

    def _emit_queue(self) -> None:
        self.bus.emit("queue", {
            "pending": [m.to_dict() for m in self.selector.pending()[:30]],
            "suggestions": [{"id": k, "text": r.text, "emotion": r.emotion,
                             "author": r.message.author if r.message else "",
                             "message": r.message.text if r.message else ""} for k, r in self.suggestions.items()],
        })
        self.bus.emit("stats", self.stats.to_dict())

    # -- worker -----------------------------------------------------------

    async def _work(self) -> None:
        while True:
            await asyncio.sleep(0.2)
            if self.state != "running" or self.phase != "idle" or self._current:
                continue
            if time.monotonic() - self._last_speech_end < self.settings.chat.min_interval:
                continue
            msg = self.selector.next()
            if msg is None:
                continue
            self._emit_queue()
            self._current = asyncio.create_task(self._answer(msg))
            try:
                await self._current
            except asyncio.CancelledError:
                if asyncio.current_task().cancelling():  # the worker itself is being stopped
                    raise
            except Exception:  # noqa: BLE001
                log.exception("answering failed")
            finally:
                self._current = None

    async def _answer(self, msg: ChatMessage, force_speak: bool = False) -> Reply | None:
        reply = await self.generate(msg)
        if reply is None:
            return None
        if self.settings.mode == "assisted" and msg.platform == "youtube" and not force_speak:
            self.suggestions[msg.id] = reply
            self._emit_queue()
            return reply
        await self.speak(reply)
        return reply

    async def approve(self, item_id: str) -> None:
        """Assisted mode: speak a suggestion. Manual selection: answer a queued message."""
        reply = self.suggestions.pop(item_id, None)
        if reply:
            self._emit_queue()
            await self._run_exclusive(self.speak(reply))
            return
        msg = self.selector.take(item_id)
        if msg:
            self._emit_queue()
            await self._run_exclusive(self._answer(msg))

    def reject(self, item_id: str) -> None:
        if self.suggestions.pop(item_id, None) is None:
            self.selector.remove(item_id)
        self._emit_queue()

    async def _run_exclusive(self, coro) -> None:
        if self._current:
            await self.interrupt()
        self._current = asyncio.create_task(coro)
        try:
            await self._current
        except asyncio.CancelledError:
            pass
        finally:
            self._current = None

    async def test_reply(self, text: str, author: str = "You") -> None:
        msg = ChatMessage(id=f"test-{uuid.uuid4().hex[:8]}", author=author, text=clean_text(text), platform="demo")
        await self._run_exclusive(self._answer(msg, force_speak=True))

    async def say(self, text: str, emotion: str = "happy") -> None:
        text = clean_text(text, 400)
        if text:
            reply = Reply(text, emotion if emotion in EMOTIONS else "neutral", 0.6, source="manual")
            await self._run_exclusive(self.speak(reply))

    async def react(self, emotion: str) -> None:
        if emotion in EMOTIONS:
            await self.server.broadcast({"type": "react", "emotion": emotion, "intensity": 1.0})

    # -- generation -------------------------------------------------------

    async def generate(self, msg: ChatMessage) -> Reply | None:
        ai = self.settings.ai
        character = self.character
        if not ai.model:
            self._error("ai", "Choose an Ollama model first.")
            return None
        cs = self.settings.character_settings()
        self._set_phase("thinking", author=msg.author, message=msg.text)
        system = self.brain.system_prompt(character, cs.personality, self.settings.context, ai.reply_language,
                                          ai.max_sentences, ai.max_chars, catchphrases=cs.catchphrases)
        messages = self.brain.messages(system, character, msg, ai.reply_language, ai.memory_size)
        started = time.monotonic()
        try:
            result = await self.ollama.chat(
                ai.model, messages, temperature=ai.temperature, max_tokens=ai.max_tokens,
                context_window=ai.context_window, schema=REPLY_SCHEMA, keep_alive=ai.keep_alive,
                timeout=ai.timeout,
            )
        except OllamaError as e:
            self.stats.ai_failures += 1
            self._error("ai", str(e))
            self._set_phase("idle")
            return None
        reply = self.brain.parse(result.text, character, ai.reply_language, ai.max_sentences, ai.max_chars,
                                 self.settings.context.forbidden_topics)
        promo = self.brain.maybe_promo(self.settings.context) if reply.source == "ai" else ""
        if promo:
            reply.text = f"{reply.text} {promo}"
        reply.message = msg
        reply.generation_seconds = time.monotonic() - started
        self.stats.generation.append(reply.generation_seconds)
        self.stats.answered += 1
        self.brain.remember(msg, reply)
        self.bus.emit("reply", {"author": msg.author, "message": msg.text, "text": reply.text,
                                "emotion": reply.emotion, "source": reply.source,
                                "seconds": round(reply.generation_seconds, 2)})
        return reply

    # -- speech -----------------------------------------------------------

    async def speak(self, reply: Reply) -> None:
        """Synthesize and play one reply. Holding the lock guarantees a single voice."""
        async with self._speech_lock:
            await self._speak_locked(reply)

    async def _speak_locked(self, reply: Reply) -> None:
        cs = self.settings.character_settings()
        vs = self.settings.voice
        uid = uuid.uuid4().hex[:12]
        utterance = None
        voice = self.voice_for() if vs.enabled else None
        if voice:
            self._set_phase("thinking", stage="voice")
            try:
                utterance = await asyncio.to_thread(self.tts.synthesize, reply.text, voice, cs.voice_rate,
                                                    cs.voice_pitch, vs.volume, uid)
                self.stats.synthesis.append(utterance.synth_seconds)
            except TTSError as e:
                self.stats.tts_failures += 1
                self._error("tts", str(e))
        duration = utterance.duration if utterance else max(2.0, len(reply.text) / 14)
        event = {
            "type": "speak", "id": uid, "text": reply.text, "emotion": reply.emotion,
            "intensity": reply.intensity, "duration": round(duration, 3),
            "author": reply.message.author if reply.message else "",
            "envelope": utterance.envelope if utterance else [], "fps": 50,
        }
        play_in_overlay = vs.audio_output == "overlay" and self.server.has_audio_sink
        self._set_phase("speaking", text=reply.text, emotion=reply.emotion)
        started = time.monotonic()
        try:
            if utterance and play_in_overlay:
                ended = await self.server.speak(event, utterance.path, play_in_overlay=True)
                if ended:
                    try:
                        await asyncio.wait_for(ended.wait(), duration + 5)
                    except asyncio.TimeoutError:
                        pass
                    self.server.forget_utterance(uid)
            else:
                if utterance:
                    self.player.play(utterance.path)
                await self.server.speak(event, None, play_in_overlay=False)
                if utterance:
                    await asyncio.to_thread(self.player.wait, duration + 5)
                else:
                    await asyncio.sleep(duration)
            self.stats.spoken += 1 if utterance else 0
            self.stats.speech.append(time.monotonic() - started)
        except asyncio.CancelledError:
            self.player.stop()
            raise
        finally:
            self._last_speech_end = time.monotonic()
            await self.server.broadcast({"type": "done", "id": uid})
            self._set_phase("idle")
            self.tts.cleanup()
        entry = {
            "time": time.time(), "author": reply.message.author if reply.message else "",
            "message": reply.message.text if reply.message else "", "reply": reply.text,
            "emotion": reply.emotion, "source": reply.source, "voice": bool(utterance),
            "generation": round(reply.generation_seconds, 2),
        }
        self.history.append(entry)
        self.bus.emit("history", entry)
        self.bus.emit("stats", self.stats.to_dict())

    # -- overlay ----------------------------------------------------------

    def _emit_overlay_config(self) -> None:
        o = self.settings.overlay
        cs = self.settings.character_settings()
        cfg = {
            "type": "config", "character": self.settings.character, "color": cs.color or self.character.color,
            "name": self.character.name, "showBubble": o.show_bubble, "showAuthor": o.show_author,
            "scale": o.scale, "x": o.position_x, "y": o.position_y, "rotation": o.rotation,
            "zoom": o.camera_zoom, "light": o.light, "shadows": o.shadows, "quality": o.quality,
            "fps": o.fps, "bubbleSeconds": o.bubble_seconds,
        }
        if self._started:
            asyncio.ensure_future(self.server.broadcast(cfg, keep=True))

    async def set_character(self, character_id: str) -> None:
        self.settings.character = get_character(character_id).id
        self.brain.forget()
        self.apply_settings()
        asyncio.create_task(self.warm_up())

    def _error(self, source: str, message: str) -> None:
        log.warning("%s: %s", source, message)
        self.bus.emit("error", {"source": source, "message": message})
