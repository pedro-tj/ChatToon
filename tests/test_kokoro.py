"""Kokoro through TTS BigLinux: the koko command line, WAV conversion, errors and cancel.

A fake ``koko`` (a small Python script) stands in for the real binary, so the real
subprocess handling — argv, working directory, timeouts, killing, reaping — is exercised.
"""

import math
import os
import struct
import sys
import threading
import time
import wave

import pytest

from chattoon.core import tts as tts_mod
from chattoon.core.tts import BigLinuxTTS, TTSCancelled, TTSError, Voice, analyse_wav, to_pcm16

DORA = Voice("kokoro:pf_dora", "Dora", "pt-BR", "kokoro", "female", "neural")

FAKE_KOKO = r'''#!{python}
import math, os, struct, sys, time
args = sys.argv[1:]
mode = os.environ.get("FAKE_KOKO", "ok")
with open(os.environ["FAKE_KOKO_LOG"], "a") as log:
    log.write(repr(args) + "|" + os.getcwd() + "\n")
if mode == "slow":
    time.sleep(30)
if mode == "fail":
    sys.stderr.write("WARNING: Character x not in vocabulary\nPHONEMIZE RESULT: abc\nthread 'main' panicked: model exploded\n")
    sys.exit(3)
out = args[args.index("-o") + 1]
if mode == "garbage":
    open(out, "wb").write(b"not a wav at all" * 20)
    sys.exit(0)
# stereo 32-bit float WAVE_FORMAT_EXTENSIBLE at 24 kHz, like koko text
rate, ch, n = 24000, 2, 12000
frames = b"".join(struct.pack("<ff", v, v) for v in
                  (0.5 * math.sin(i / 7) if 3000 < i < 9000 else 0.0 for i in range(n)))
fmt = struct.pack("<HHIIHHHHIH14s", 0xFFFE, ch, rate, rate * ch * 4, ch * 4, 32, 22, 32, 3, 3,
                  b"\x00\x00\x00\x00\x10\x00\x80\x00\x00\xaa\x00\x38\x9b\x71")
body = b"WAVE" + b"fmt " + struct.pack("<I", len(fmt)) + fmt + b"data" + struct.pack("<I", len(frames)) + frames
open(out, "wb").write(b"RIFF" + struct.pack("<I", len(body)) + body)
sys.stderr.write("shape_style: [1, 256]\nAudio saved to " + out + "\n")
'''


class FakeKokoroService:
    """The functions ChatToon uses from TTS BigLinux's services/kokoro_voice_service.py."""

    def __init__(self, koko, workdir, problem=""):
        self.koko, self.workdir, self.problem, self.mode = koko, workdir, problem, "text"
        self.problem_calls = []

    def koko_problem(self, voice_id, blend=""):
        self.problem_calls.append(voice_id)
        return self.problem

    def prepare_koko_text(self, text, limit=220):
        return text.replace("?!", "?").replace(". ", ".\n")

    def kokoro_speed(self, rate, emotion="neutral"):
        return max(0.5, min(2.0, 1.0 + rate / 100))

    def koko_workdir(self):
        return str(self.workdir)

    def build_koko_command(self, voice_id, *, speed=1.0, text=None, output=None, **kw):
        # run through the interpreter: /tmp may be mounted noexec
        cmd = [sys.executable, str(self.koko), "-s", voice_id.removeprefix("kokoro:"), "-p", f"{speed:.2f}"]
        if self.mode == "pipe" or text is None:
            return cmd + ["pipe", "-o", output or "x.wav"]
        return cmd + ["text", "-o", output, "--", text]


@pytest.fixture
def kokoro(tmp_path, monkeypatch):
    koko = tmp_path / "koko"
    koko.write_text(FAKE_KOKO.replace("{python}", sys.executable))
    log = tmp_path / "koko.log"
    monkeypatch.setenv("FAKE_KOKO_LOG", str(log))
    monkeypatch.setenv("FAKE_KOKO", "ok")
    workdir = tmp_path / "kokowork"
    workdir.mkdir()
    t = BigLinuxTTS(tmp_path / "w")
    svc = type("Svc", (), {"volume_factor": staticmethod(lambda v: v / 50)})
    t._modules = (None, svc, lambda text, **kw: text, None)  # voice_manager, tts_service, process_text, engine
    t._kokoro = FakeKokoroService(koko, workdir)
    t.log = log
    yield t
    t.shutdown()


def calls(t):
    return [line.split("|") for line in t.log.read_text().splitlines()] if t.log.exists() else []


def test_kokoro_renders_with_koko_text_and_converts_to_pcm16(kokoro):
    u = kokoro.synthesize("Maria perguntou: Funciona?! Sim.", DORA, rate=50, volume=85, utterance_id="k1")
    argv, cwd = calls(kokoro)[0]
    assert "'text'" in argv and "'pipe'" not in argv  # renders a file, never plays by itself
    assert "'pf_dora'" in argv and "'1.50'" in argv  # the chosen voice and the speed mapping
    assert "'--', 'Maria perguntou: Funciona? Sim.'" in argv  # prepared text, after "--"
    assert cwd == str(kokoro._kokoro.workdir)  # koko writes scratch files to a private directory
    with wave.open(str(u.path)) as w:
        assert (w.getnchannels(), w.getsampwidth(), w.getframerate()) == (1, 2, 24000)
    assert u.duration == pytest.approx(0.5, abs=0.01)
    assert len(u.envelope) == 25 and max(u.envelope) > 0.8 and u.envelope[0] == 0.0  # lip sync data
    assert not list(kokoro.workdir.glob("*.koko.wav"))  # raw float file removed


def test_kokoro_unavailable_voice_or_model_is_reported(kokoro):
    kokoro._kokoro.problem = "This Kokoro voice is not installed. Open the Voice Manager to download it."
    with pytest.raises(TTSError) as err:
        kokoro.synthesize("Oi", DORA)
    assert err.value.code == "kokoro-unavailable" and "Voice Manager" in str(err.value)
    assert calls(kokoro) == []  # koko never started


def test_kokoro_failure_reports_the_real_error_not_the_noise(kokoro, monkeypatch):
    monkeypatch.setenv("FAKE_KOKO", "fail")
    with pytest.raises(TTSError) as err:
        kokoro.synthesize("Oi", DORA)
    assert err.value.code == "kokoro-failed"
    assert "model exploded" in err.value.detail and "PHONEMIZE" not in err.value.detail  # the text read stays private


def test_kokoro_invalid_wav(kokoro, monkeypatch):
    monkeypatch.setenv("FAKE_KOKO", "garbage")
    with pytest.raises(TTSError) as err:
        kokoro.synthesize("Oi", DORA, utterance_id="g")
    assert err.value.code == "invalid-wav"
    assert not list(kokoro.workdir.glob("g*"))  # nothing half-written is left behind


def test_kokoro_never_uses_a_mode_that_plays_audio(kokoro):
    kokoro._kokoro.mode = "pipe"  # an incompatible TTS BigLinux would play it AND hand us the file
    with pytest.raises(TTSError) as err:
        kokoro.synthesize("Oi", DORA)
    assert err.value.code == "kokoro-failed" and calls(kokoro) == []


def test_kokoro_cancel_kills_and_reaps_the_process(kokoro, monkeypatch):
    monkeypatch.setenv("FAKE_KOKO", "slow")
    result = {}

    def run():
        try:
            kokoro.synthesize("Uma frase longa", DORA)
            result["r"] = "finished"
        except TTSCancelled:
            result["r"] = "cancelled"

    th = threading.Thread(target=run)
    th.start()
    for _ in range(200):
        if kokoro._proc is not None:
            break
        time.sleep(0.01)
    proc = kokoro._proc
    started = time.monotonic()
    kokoro.cancel()
    th.join(5)
    assert result == {"r": "cancelled"} and time.monotonic() - started < 3
    assert proc.poll() is not None  # reaped: no zombie, no orphan
    with pytest.raises(ProcessLookupError):
        os.kill(proc.pid, 0)


def test_cancel_also_drops_a_synthesis_waiting_for_the_engine(kokoro):
    kokoro._lock.acquire()  # another synthesis is running
    result = {}

    def run():
        try:
            kokoro.synthesize("depois", DORA)
            result["r"] = "finished"
        except TTSCancelled:
            result["r"] = "cancelled"

    th = threading.Thread(target=run)
    th.start()
    time.sleep(0.1)
    kokoro.cancel()
    kokoro._lock.release()
    th.join(5)
    assert result == {"r": "cancelled"} and calls(kokoro) == []  # koko was never started for it


def test_kokoro_timeout(kokoro, monkeypatch):
    monkeypatch.setenv("FAKE_KOKO", "slow")
    monkeypatch.setattr(tts_mod, "KOKORO_TIMEOUT_BASE", 0.5)
    monkeypatch.setattr(tts_mod, "KOKORO_TIMEOUT_PER_CHAR", 0.0)
    started = time.monotonic()
    with pytest.raises(TTSError) as err:
        kokoro.synthesize("Oi", DORA)
    assert err.value.code == "kokoro-timeout" and time.monotonic() - started < 5
    assert kokoro._proc is None


def test_kokoro_voice_has_no_pitch_control():
    assert DORA.to_dict()["pitch"] is False
    assert Voice("piper:/x.onnx", "Faber", "pt-BR", "piper").to_dict()["pitch"] is True


# -- WAV normalisation -------------------------------------------------------

def _riff(fmt_body, data):
    body = b"WAVE" + b"fmt " + struct.pack("<I", len(fmt_body)) + fmt_body + b"data" + struct.pack("<I", len(data)) + data
    return b"RIFF" + struct.pack("<I", len(body)) + body


@pytest.mark.parametrize("bits,tag,pack", [
    (16, 1, lambda v: struct.pack("<h", int(v * 32767))),
    (32, 3, lambda v: struct.pack("<f", v)),
    (8, 1, lambda v: bytes([int(128 + v * 127)])),
    (24, 1, lambda v: int(v * 8388607).to_bytes(3, "little", signed=True)),
])
def test_to_pcm16_accepts_common_formats(tmp_path, bits, tag, pack):
    rate, ch = 16000, 2
    data = b"".join(pack(0.4 * math.sin(i / 5)) * ch for i in range(rate // 2))
    src = tmp_path / "in.wav"
    src.write_bytes(_riff(struct.pack("<HHIIHH", tag, ch, rate, rate * ch * bits // 8, ch * bits // 8, bits), data))
    to_pcm16(src)
    with wave.open(str(src)) as w:
        assert (w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()) == (1, 2, rate, rate // 2)
    duration, env = analyse_wav(src)
    assert duration == pytest.approx(0.5) and max(env) > 0.8


def test_to_pcm16_streaming_header_and_gain_never_clips(tmp_path):
    data = b"".join(struct.pack("<f", 0.9 * math.sin(i / 3)) for i in range(8000))
    src = tmp_path / "s.wav"
    raw = bytearray(_riff(struct.pack("<HHIIHH", 3, 1, 16000, 64000, 4, 32), data))
    raw[-len(data) - 4:-len(data)] = b"\xff\xff\xff\xff"  # "unknown length", as streaming engines write
    src.write_bytes(bytes(raw))
    to_pcm16(src, gain=2.0)  # 0.9 * 2 would clip: limited to the peak
    with wave.open(str(src)) as w:
        samples = struct.unpack(f"<{w.getnframes()}h", w.readframes(w.getnframes()))
    assert len(samples) == 8000 and 31000 < max(samples) < 32767


@pytest.mark.parametrize("payload", [b"", b"RIFF\x00\x00\x00\x00WAVE", b"hello world, not audio" * 5])
def test_to_pcm16_rejects_broken_files(tmp_path, payload):
    src = tmp_path / "bad.wav"
    src.write_bytes(payload)
    with pytest.raises(TTSError) as err:
        to_pcm16(src)
    assert err.value.code == "invalid-wav"


# -- real engine (needs biglinux-kokoro-tts and --run-live) ------------------------

@pytest.mark.live
@pytest.mark.parametrize("voice_id", ["kokoro:pf_dora", "kokoro:pm_alex"])
def test_real_kokoro_voice(tmp_path, voice_id):
    t = BigLinuxTTS(tmp_path / "w")
    voice = t.find(voice_id)
    if voice is None:
        pytest.skip(f"{voice_id} is not installed")
    short = t.synthesize("Maria perguntou: Por que o Windows trava tanto?!", voice, volume=85)
    long = t.synthesize("Carlos, essa pergunta é mais fácil que instalar um pacote no BigLinux. " * 3, voice, rate=30)
    for u in (short, long):
        with wave.open(str(u.path)) as w:
            assert (w.getnchannels(), w.getsampwidth()) == (1, 2)
        assert u.duration > 1.0 and max(u.envelope) > 0.5
    assert long.duration > short.duration
    t.shutdown()


def test_engine_that_cannot_start_is_a_tts_error(kokoro, tmp_path):
    kokoro._kokoro.build_koko_command = lambda *a, **k: [str(tmp_path / "missing-koko"), "text", "-o", "x"]
    with pytest.raises(TTSError) as err:
        kokoro.synthesize("Oi", DORA)
    assert err.value.code == "failed" and kokoro._proc is None
