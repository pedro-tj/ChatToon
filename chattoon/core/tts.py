"""Speech through TTS BigLinux (https://github.com/biglinux/tts-biglinux).

ChatToon does not ship its own speech engine. It imports TTS BigLinux's modules from
the installed package to reuse its voice catalog (RHVoice, espeak-ng, Piper, Kokoro),
its text normalisation (abbreviations, numbers, URLs, Markdown) and its native
``tts_engine`` synthesizer. The only difference from the TTS BigLinux app is the last
step: instead of piping audio straight to ``aplay``, ChatToon renders a WAV file so it
can compute a mouth-movement envelope and play the audio exactly once, in one place.
"""

from __future__ import annotations

import array
import json
import logging
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import wave
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)

TTS_BIGLINUX_DIR = Path(os.environ.get("CHATTOON_TTS_BIGLINUX_DIR", "/usr/share/biglinux/tts-biglinux"))
TTS_ENGINE_DIR = Path(os.environ.get("CHATTOON_TTS_ENGINE_DIR", "/usr/lib/tts-biglinux"))
TTS_BIGLINUX_SETTINGS = Path.home() / ".config" / "biglinux-tts" / "settings.json"
ENVELOPE_FPS = 50  # mouth openness samples per second


class TTSError(Exception):
    pass


@dataclass(frozen=True)
class Voice:
    id: str
    name: str
    language: str
    backend: str
    gender: str = ""
    quality: str = ""

    @property
    def label(self) -> str:
        engine = {"rhvoice": "RHVoice", "espeak-ng": "espeak-ng", "piper": "Piper", "kokoro": "Kokoro"}
        return f"{self.name} · {engine.get(self.backend, self.backend)}"


@dataclass
class Utterance:
    id: str
    text: str
    path: Path
    duration: float
    envelope: list[float]  # 0..1 mouth openness at ENVELOPE_FPS
    synth_seconds: float = 0.0


class BigLinuxTTS:
    """Adapter around the installed TTS BigLinux package."""

    def __init__(self, workdir: Path | None = None):
        self.workdir = Path(workdir or tempfile.mkdtemp(prefix="chattoon-tts-"))
        self.workdir.mkdir(parents=True, exist_ok=True)
        os.chmod(self.workdir, 0o700)
        self._lock = threading.Lock()  # the native engine is not re-entrant
        self._voices: list[Voice] | None = None
        self._modules = None
        self.error = ""

    # -- integration ------------------------------------------------------

    def _load(self):
        if self._modules is not None:
            return self._modules
        if not TTS_BIGLINUX_DIR.is_dir():
            self.error = "TTS BigLinux is not installed (package tts-biglinux)."
            raise TTSError(self.error)
        for p in (str(TTS_BIGLINUX_DIR), str(TTS_ENGINE_DIR)):
            if p not in sys.path:
                sys.path.append(p)  # append: never shadow ChatToon's own modules
        try:
            from services import tts_service, voice_manager  # type: ignore[import-not-found]
            from services.text_processor import process_text  # type: ignore[import-not-found]
        except Exception as e:  # noqa: BLE001 - any import failure means "unusable"
            self.error = f"Could not load TTS BigLinux: {e}"
            raise TTSError(self.error) from e
        try:
            import tts_engine  # type: ignore[import-not-found]
        except ImportError:
            tts_engine = None
        self._modules = (voice_manager, tts_service, process_text, tts_engine)
        return self._modules

    @property
    def available(self) -> bool:
        try:
            self._load()
            return True
        except TTSError:
            return False

    def voices(self, refresh: bool = False) -> list[Voice]:
        if self._voices is None or refresh:
            vm = self._load()[0]
            catalog = vm.discover_voices()
            usable = {k for k, v in vm.engine_availability(catalog).items() if getattr(v, "value", v) == "ready"}
            self._voices = [
                Voice(v.voice_id, v.name, v.language, v.backend, v.gender or "", v.quality or "")
                for v in catalog.voices if v.backend in usable
            ]
        return self._voices

    def find(self, voice_id: str) -> Voice | None:
        return next((v for v in self.voices() if v.id == voice_id), None)

    def user_default(self) -> Voice | None:
        """The voice chosen in the TTS BigLinux app, if any."""
        try:
            data = json.loads(TTS_BIGLINUX_SETTINGS.read_text(encoding="utf-8"))
            speech = data.get("speech", data)
            return self.find(speech.get("voice_id", ""))
        except (OSError, ValueError, AttributeError):
            return None

    def suggest(self, hints: tuple[str, ...], language: str = "pt-BR") -> Voice | None:
        voices = self.voices()
        lang = language.lower()
        same_lang = [v for v in voices if v.language.lower() == lang] or \
                    [v for v in voices if v.language.lower().split("-")[0] == lang.split("-")[0]]
        for hint in hints:
            for v in same_lang:
                if hint.casefold() in (v.id + " " + v.name).casefold():
                    return v
        default = self.user_default()
        if default and default in same_lang:
            return default
        return same_lang[0] if same_lang else (voices[0] if voices else None)

    # -- synthesis --------------------------------------------------------

    def prepare_text(self, text: str, language: str) -> str:
        process_text = self._load()[2]
        text = re.sub(r"[\U0001F000-\U0001FAFF☀-➿️]", " ", text)
        processed = process_text(text, expand_abbreviations=True, process_special_chars=False,
                                 process_urls=False, strip_formatting=True, normalize_numbers=True,
                                 language=language)
        return " ".join((processed or "").split())

    def prewarm(self, voice: Voice) -> None:
        """Load a Piper model ahead of time (first synthesis drops from ~1.6 s to ~0.1 s)."""
        engine = self._load()[3]
        if voice.backend == "piper" and engine is not None and hasattr(engine, "load_piper"):
            model = voice.id.removeprefix("piper:")
            if not model.endswith(".onnx") and os.path.isfile(model + ".onnx"):
                model += ".onnx"
            with self._lock:
                engine.load_piper(model)

    def synthesize(self, text: str, voice: Voice, rate: int = 0, pitch: int = 0, volume: int = 85,
                   utterance_id: str = "") -> Utterance:
        """Render ``text`` to a WAV file (blocking: call from a worker thread)."""
        _, svc, _, engine = self._load()
        spoken = self.prepare_text(text, voice.language)
        if not spoken:
            raise TTSError("Nothing to say after text cleanup")
        uid = utterance_id or f"u{int(time.time() * 1000)}"
        path = self.workdir / f"{uid}.wav"
        started = time.monotonic()
        with self._lock:
            if voice.backend == "piper":
                self._piper(svc, engine, spoken, voice, rate, pitch, volume, path)
            elif voice.backend == "espeak-ng":
                self._espeak(svc, engine, spoken, voice, rate, pitch, volume, path)
            elif voice.backend == "rhvoice":
                self._rhvoice(spoken, voice, rate, pitch, volume, path)
            else:
                raise TTSError(f"Voice engine '{voice.backend}' is not supported by ChatToon yet")
        if not path.exists() or path.stat().st_size < 100:
            raise TTSError("The voice engine produced no audio")
        duration, envelope = analyse_wav(path)
        return Utterance(uid, text, path, duration, envelope, time.monotonic() - started)

    @staticmethod
    def _write(path: Path, data: bytes) -> None:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "wb") as f:
            f.write(data)

    def _piper(self, svc, engine, text, voice, rate, pitch, volume, path) -> None:
        model = voice.id.removeprefix("piper:")
        if not model.endswith(".onnx") and os.path.isfile(model + ".onnx"):
            model += ".onnx"
        if not os.path.isfile(model):
            raise TTSError("The selected Piper voice is not installed")
        args = (svc.piper_length_scale(rate), svc.piper_noise_scale(pitch), 0.8, svc.volume_factor(volume))
        if engine is not None:
            wav = engine.synthesize_piper(text, model, *args)
            if wav and len(wav) >= 100:
                self._write(path, bytes(wav))
                return
        from services.voice_manager import _find_piper_binary  # type: ignore[import-not-found]

        binary = _find_piper_binary()
        if not binary:
            raise TTSError("Piper is not installed")
        self._run([binary, "--model", model, "--output_file", str(path), "--length_scale", f"{args[0]:.2f}",
                   "--noise_scale", f"{args[1]:.3f}", "--noise_w", "0.8"], text)

    def _espeak(self, svc, engine, text, voice, rate, pitch, volume, path) -> None:
        name = voice.id.removeprefix("espeak-") or "pt-br"
        wpm, esp_pitch, amp = svc.espeak_wpm(rate), svc.espeak_pitch(pitch), svc.espeak_volume(volume)
        if engine is not None and hasattr(engine, "synthesize_espeak"):
            wav = engine.synthesize_espeak(text, name, wpm, esp_pitch, amp)
            if wav and len(wav) >= 100:
                self._write(path, bytes(wav))
                return
        self._run(["espeak-ng", "-v", name, "-s", str(wpm), "-p", str(esp_pitch), "-a", str(amp),
                   "-w", str(path), "--stdin"], text)

    def _rhvoice(self, text, voice, rate, pitch, volume, path) -> None:
        # Same parameter mapping TTS BigLinux uses for RHVoice-test.
        self._run(["RHVoice-test", "-p", voice.id, "-r", str(max(20, min(300, 100 + rate))),
                   "-t", str(max(20, min(200, 100 + pitch))), "-v", str(max(0, min(100, volume))),
                   "-o", str(path)], text)

    @staticmethod
    def _run(cmd: list[str], text: str) -> None:
        if not shutil.which(cmd[0]) and not os.path.isfile(cmd[0]):
            raise TTSError(f"{cmd[0]} is not installed")
        # Text goes through stdin, never through a shell or the command line.
        result = subprocess.run(cmd, input=text.encode("utf-8"), capture_output=True, timeout=120)
        if result.returncode != 0:
            raise TTSError(result.stderr.decode("utf-8", "replace").strip()[-300:] or f"{cmd[0]} failed")

    def cleanup(self, keep: int = 20) -> None:
        """Delete old WAV files, keeping the newest ``keep``."""
        files = sorted(self.workdir.glob("*.wav"), key=lambda p: p.stat().st_mtime, reverse=True)
        for old in files[keep:]:
            old.unlink(missing_ok=True)

    def shutdown(self) -> None:
        shutil.rmtree(self.workdir, ignore_errors=True)


def analyse_wav(path: Path, fps: int = ENVELOPE_FPS) -> tuple[float, list[float]]:
    """Duration and normalised loudness envelope (0..1) of a 16-bit PCM WAV."""
    with wave.open(str(path), "rb") as w:
        rate, channels, width, frames = w.getframerate(), w.getnchannels(), w.getsampwidth(), w.getnframes()
        raw = w.readframes(frames)
    duration = frames / rate if rate else 0.0
    if width != 2 or not raw:
        return duration, []
    samples = array.array("h", raw[: len(raw) - len(raw) % 2])
    if sys.byteorder == "big":
        samples.byteswap()
    step = max(1, int(rate / fps)) * channels
    levels = []
    for i in range(0, len(samples), step):
        window = samples[i:i + step]
        if window:
            levels.append(math.sqrt(sum(s * s for s in window) / len(window)))
    if not levels:
        return duration, []
    ref = sorted(levels)[int(len(levels) * 0.95)] or 1.0  # 95th percentile, robust to peaks
    gate = ref * 0.08
    return duration, [round(min(1.0, max(0.0, (v - gate) / (ref - gate))), 3) if ref > gate else 0.0
                      for v in levels]


class AudioPlayer:
    """Plays one WAV at a time on the desktop (PipeWire/PulseAudio/ALSA)."""

    CANDIDATES = (["pw-play"], ["paplay"], ["aplay", "-q"])

    def __init__(self):
        self._proc: subprocess.Popen | None = None
        self._lock = threading.Lock()
        self.command = next((c for c in self.CANDIDATES if shutil.which(c[0])), None)

    @property
    def available(self) -> bool:
        return self.command is not None

    def play(self, path: Path) -> None:
        """Start playback (stopping anything still playing)."""
        if not self.command:
            raise TTSError("No audio player found (pipewire, pulseaudio-utils or alsa-utils)")
        with self._lock:
            self._stop_locked()
            self._proc = subprocess.Popen([*self.command, str(path)], stdout=subprocess.DEVNULL,
                                          stderr=subprocess.DEVNULL)

    def wait(self, timeout: float | None = None) -> bool:
        """Block until playback ends. True if it finished on its own."""
        proc = self._proc
        if proc is None:
            return True
        try:
            return proc.wait(timeout) == 0
        except subprocess.TimeoutExpired:
            return False

    @property
    def playing(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def stop(self) -> None:
        with self._lock:
            self._stop_locked()

    def _stop_locked(self) -> None:
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()
            try:
                self._proc.wait(1)
            except subprocess.TimeoutExpired:
                self._proc.kill()
        self._proc = None
