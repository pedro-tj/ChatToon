"""Voice engines through TTS BigLinux's own modules (docs/INTELLIGENCE.md).
TTS BigLinux is faked: nothing is installed or downloaded."""

import sys
import types
from dataclasses import dataclass, field
from enum import Enum

import pytest

from chattoon.core import tts_manager
from chattoon.core.tts import BigLinuxTTS


class Avail(str, Enum):
    NOT_INSTALLED = "not-installed"
    NO_VOICES = "no-voices"
    READY = "ready"


@dataclass
class V:
    voice_id: str
    name: str
    language: str
    backend: str
    gender: str = ""
    quality: str = ""


@dataclass
class Catalog:
    voices: list = field(default_factory=list)

    def get_by_backend(self, b):
        return [v for v in self.voices if v.backend == b]


class FakeTTS(BigLinuxTTS):
    def __init__(self, tmp, voices, availability, installed=True):
        super().__init__(tmp)
        self._installed = installed
        vm = types.SimpleNamespace(discover_voices=lambda: Catalog(voices),
                                   engine_availability=lambda cat: {k: Avail(v) for k, v in availability.items()})
        self._fake = (vm, None, None, None)
        self.refreshed = 0

    def _load(self):
        if not self._installed:
            from chattoon.core.tts import TTSError
            self.error = "TTS BigLinux is not installed (package tts-biglinux)."
            raise TTSError(self.error)
        return self._fake

    def voices(self, refresh=False):
        self.refreshed += refresh
        return self._voices or []


def test_states_tell_program_voice_and_language_apart(tmp_path):
    voices = [V("piper:/x/pt_BR-faber", "Faber", "pt-BR", "piper"), V("kokoro:af_heart", "Heart", "en-US", "kokoro"),
              V("espeak-pt-br", "Portuguese", "pt-BR", "espeak-ng")]
    tts = FakeTTS(tmp_path, voices, {"piper": "ready", "kokoro": "ready", "rhvoice": "not-installed",
                                     "espeak-ng": "ready"})
    s = tts_manager.states(tts, "pt-BR")
    e = s["engines"]
    assert s["installed"] and e["piper"]["state"] == "ready" and e["piper"]["inLanguage"] == 1
    assert e["kokoro"]["state"] == "needs_voice"  # installed, but only an English voice
    assert e["rhvoice"]["state"] == "not_installed" and e["rhvoice"]["voicePackage"] == "rhvoice-voice-leticia-f123"
    assert e["espeak-ng"]["state"] == "ready"
    assert {v.id for v in tts._voices} == {v.voice_id for v in voices}  # the voice cache was refreshed too
    tts.shutdown()


def test_engine_without_voices_needs_a_voice(tmp_path):
    tts = FakeTTS(tmp_path, [], {"piper": "no-voices", "kokoro": "not-installed", "rhvoice": "not-installed",
                                 "espeak-ng": "not-installed"})
    assert tts_manager.states(tts, "pt-BR")["engines"]["piper"]["state"] == "needs_voice"
    tts.shutdown()


def test_missing_tts_biglinux(tmp_path):
    tts = FakeTTS(tmp_path, [], {}, installed=False)
    s = tts_manager.states(tts, "pt-BR")
    assert not s["installed"] and all(e["state"] == "unavailable" for e in s["engines"].values())
    tts.shutdown()


@pytest.fixture
def installer(monkeypatch):
    calls = {"install": [], "aur": []}

    @dataclass
    class Res:
        wanted: str
        name: str = ""
        source: str = ""

    @dataclass
    class Result:
        ok: bool
        message: str = ""
        detail: str = ""

    def resolve(packages):
        table = {"piper-tts-bin": ("piper-tts-bin", "installed"), "piper-voices-pt-BR": ("piper-voices-pt-br", "repo"),
                 "biglinux-kokoro-tts": ("biglinux-kokoro-tts", "aur")}
        return [Res(p, *table.get(p, ("", ""))) for p in packages]

    module = types.SimpleNamespace(
        resolve=resolve, query=lambda name: types.SimpleNamespace(download_size="222.39 MiB"),
        install=lambda names: calls["install"].append(names) or Result(True),
        install_aur=lambda names: calls["aur"].append(names) or Result(True), InstallResult=Result)
    services = types.ModuleType("services")
    services.package_installer = module
    monkeypatch.setitem(sys.modules, "services", services)
    monkeypatch.setitem(sys.modules, "services.package_installer", module)
    return calls


def test_plan_and_install_reuse_tts_biglinux_installer(tmp_path, installer):
    tts = FakeTTS(tmp_path, [], {})
    plan = tts_manager.plan(tts, "piper", "pt-BR")
    assert [(i["name"], i["source"]) for i in plan["items"]] == [("piper-tts-bin", "installed"),
                                                                  ("piper-voices-pt-br", "repo")]
    assert plan["items"][1]["size"] == "222.39 MiB"
    result = tts_manager.install(tts, "piper", plan["items"])
    assert result["ok"] and installer["install"] == [["piper-voices-pt-br"]] and tts.refreshed == 1
    kokoro = tts_manager.plan(tts, "kokoro", "pt-BR")
    tts_manager.install(tts, "kokoro", kokoro["items"])
    assert installer["aur"] == [["biglinux-kokoro-tts"]]  # AUR only through TTS BigLinux's helper
    tts.shutdown()


def test_install_refuses_packages_outside_the_engine(tmp_path, installer):
    tts = FakeTTS(tmp_path, [], {})
    result = tts_manager.install(tts, "piper", [{"name": "evil", "source": "repo"}])
    assert not result["ok"] and installer["install"] == []
    tts.shutdown()
