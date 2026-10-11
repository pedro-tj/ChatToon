"""Persistent settings (XDG), per-character settings and stream profiles."""

from __future__ import annotations

import json
import os
import secrets
import types
import typing
from dataclasses import asdict, dataclass, field, fields, is_dataclass
from pathlib import Path

APP_ID = "chattoon"


def _xdg(var: str, fallback: str) -> Path:
    return Path(os.environ.get(var) or Path.home() / fallback) / APP_ID


def config_dir() -> Path:
    return _xdg("XDG_CONFIG_HOME", ".config")


def data_dir() -> Path:
    return _xdg("XDG_DATA_HOME", ".local/share")


def cache_dir() -> Path:
    return _xdg("XDG_CACHE_HOME", ".cache")


@dataclass
class Personality:
    preset: str = "comedian"  # friendly | comedian | troll | geek | chaotic | custom
    humor: int = 75  # 0..100
    sarcasm: int = 45
    irony: int = 45
    creativity: int = 70
    energy: int = 65
    formality: int = 15
    memes: int = 40
    geek: int = 40
    provocation: int = 35
    length: str = "short"  # short | medium
    custom_prompt: str = ""  # extra instructions written by the streamer


@dataclass
class CharacterSettings:
    personality: Personality = field(default_factory=Personality)
    voice_id: str = ""  # "" = default voice suggested for the character
    voice_rate: int = 0  # -100..100 (TTS BigLinux scale)
    voice_pitch: int = 0
    catchphrases: list[str] = field(default_factory=list)
    color: str = ""  # "" = character default


@dataclass
class ChannelContext:
    channel_name: str = ""
    host_name: str = ""
    topic: str = ""
    description: str = ""
    allowed_topics: str = ""
    forbidden_topics: str = "política partidária, religião, conteúdo sexual"
    guests: str = ""
    links: str = ""
    catchphrases: str = ""
    promo_enabled: bool = True
    promo_messages: list[str] = field(default_factory=lambda: [
        "Deixa o like!", "Compartilha a live!", "Se inscreve no canal!",
    ])
    promo_every: int = 6  # at most one promo every N replies
    promo_cooldown: int = 300  # and never twice within this many seconds


@dataclass
class AISettings:
    host: str = "http://127.0.0.1:11434"
    model: str = ""
    temperature: float = 0.9
    max_tokens: int = 160
    context_window: int = 4096
    timeout: int = 60
    keep_alive: str = "15m"
    max_sentences: int = 3
    max_chars: int = 240
    reply_language: str = "pt-BR"
    memory_size: int = 4  # recent exchanges sent as context (each costs prompt-eval time)


@dataclass
class VoiceSettings:
    enabled: bool = True
    volume: int = 85  # 0..100
    audio_output: str = "desktop"  # desktop (app plays) | overlay (OBS browser source plays)


@dataclass
class ChatSettings:
    url: str = ""
    selection: str = "smart"  # all | smart | mentions | questions | moderators | members | random | manual
    user_cooldown: int = 60  # seconds before answering the same person again
    max_queue: int = 40
    message_ttl: int = 120  # older messages are dropped
    min_interval: int = 4  # seconds of silence between replies
    max_message_chars: int = 300
    skip_backlog: bool = True  # ignore messages that existed before connecting
    ignore_commands: bool = True  # "!cmd" messages belong to other bots
    blocked_words: str = ""  # comma separated, messages containing them are dropped
    superchat_priority: bool = True


@dataclass
class OverlaySettings:
    port: int = 8765
    token: str = ""
    show_bubble: bool = True
    show_author: bool = True
    scale: float = 1.0
    position_x: float = 0.0  # -1..1 (left..right)
    position_y: float = -0.15  # -1..1 (bottom..top)
    rotation: float = 0.0  # degrees around Y
    camera_zoom: float = 1.0
    light: float = 1.0
    shadows: bool = True
    quality: str = "high"  # low | medium | high
    fps: int = 60
    bubble_seconds: float = 2.5  # bubble stays this long after speech ends
    background: str = "transparent"  # transparent | green (chroma key)

    def __post_init__(self) -> None:
        if not self.token:
            self.token = secrets.token_urlsafe(12)


@dataclass
class Settings:
    character: str = "worm"  # worm | alien | tux
    mode: str = "demo"  # demo | assisted | auto
    ui_language: str = "system"  # system | en | pt_BR
    theme: str = "system"  # system | dark | light
    first_run_done: bool = False
    ai: AISettings = field(default_factory=AISettings)
    voice: VoiceSettings = field(default_factory=VoiceSettings)
    chat: ChatSettings = field(default_factory=ChatSettings)
    overlay: OverlaySettings = field(default_factory=OverlaySettings)
    context: ChannelContext = field(default_factory=ChannelContext)
    characters: dict[str, CharacterSettings] = field(default_factory=dict)

    def character_settings(self, character_id: str | None = None) -> CharacterSettings:
        from .characters import CHARACTERS  # local import: avoids a cycle

        cid = character_id or self.character
        if cid not in self.characters:
            base = CHARACTERS.get(cid)
            self.characters[cid] = base.default_settings() if base else CharacterSettings()
        return self.characters[cid]

    # -- persistence -----------------------------------------------------

    @classmethod
    def file(cls) -> Path:
        return config_dir() / "settings.json"

    @classmethod
    def load(cls, path: Path | None = None) -> Settings:
        path = path or cls.file()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return cls()
        return from_dict(cls, data)

    def save(self, path: Path | None = None) -> None:
        path = path or self.file()
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(asdict(self), ensure_ascii=False, indent=2), encoding="utf-8")
        os.chmod(tmp, 0o600)
        tmp.replace(path)

    # -- profiles (export/import without secrets) -------------------------

    def export_profile(self) -> dict:
        data = asdict(self)
        data["overlay"].pop("token", None)  # the overlay token is a local secret
        data.pop("first_run_done", None)
        return {"chattoon_profile": 1, "settings": data}

    def import_profile(self, profile: dict) -> Settings:
        if not isinstance(profile, dict) or profile.get("chattoon_profile") != 1:
            raise ValueError("not a ChatToon profile")
        data = dict(profile.get("settings") or {})
        data.setdefault("overlay", {})["token"] = self.overlay.token
        data["first_run_done"] = self.first_run_done
        return from_dict(Settings, data)


def profiles_dir() -> Path:
    return config_dir() / "profiles"


# -- tolerant (de)serialization ------------------------------------------------

def from_dict(cls, data):
    """Build dataclass ``cls`` from ``data`` ignoring unknown keys and bad types."""
    if not isinstance(data, dict):
        return cls()
    hints = typing.get_type_hints(cls)
    kwargs = {}
    for f in fields(cls):
        if f.name not in data:
            continue
        value = _coerce(hints[f.name], data[f.name])
        if value is not _INVALID:
            kwargs[f.name] = value
    return cls(**kwargs)


_INVALID = object()


def _coerce(tp, value):
    origin = typing.get_origin(tp)
    if is_dataclass(tp):
        return from_dict(tp, value) if isinstance(value, dict) else _INVALID
    if origin is dict:
        _, vt = typing.get_args(tp)
        if not isinstance(value, dict):
            return _INVALID
        out = {}
        for k, v in value.items():
            cv = _coerce(vt, v)
            if cv is not _INVALID:
                out[str(k)] = cv
        return out
    if origin is list:
        (it,) = typing.get_args(tp)
        if not isinstance(value, list):
            return _INVALID
        return [c for c in (_coerce(it, v) for v in value) if c is not _INVALID]
    if origin in (typing.Union, types.UnionType):
        return value
    if tp is bool:
        return value if isinstance(value, bool) else _INVALID
    if tp in (int, float):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return _INVALID
        return tp(value)
    if tp is str:
        return value if isinstance(value, str) else _INVALID
    return value
