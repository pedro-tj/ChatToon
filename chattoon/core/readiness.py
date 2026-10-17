"""What the character can really do right now — the report shown when Start is pressed
(docs/ARCHITECTURE.md).

Facts only, as codes (the interface words them in its language). ``blocking`` problems keep
the live from starting; ``warnings`` are optional features left off or missing.
Nothing here includes tokens, addresses or credentials.
"""

from __future__ import annotations

import time

from .characters import get_character
from .config import Settings


def _ai(settings: Settings, services: dict, service: dict) -> dict:
    ollama = services.get("ollama") or {}
    chat_models = list(ollama.get("models") or [])
    catalog = {m.get("name"): m for m in ollama.get("catalog") or []}
    model = settings.ai.model
    out = {"model": model, "version": ollama.get("version", ""), "local": service.get("local", True),
           "responded": None, "seconds": 0.0, "status": "ok", "code": "ready"}
    if not ollama.get("ok"):
        state = service.get("state", "")
        out.update(status="error", code={"not_installed": "ollama-not-installed", "stopped": "ollama-stopped",
                                         "remote": "ollama-remote-down"}.get(state, "ollama-unreachable"))
    elif not model:
        out.update(status="error", code="no-model" if chat_models else "no-chat-model")
    elif model not in chat_models:
        info = catalog.get(model)
        out.update(status="error", code="model-incompatible" if info else "model-missing")
    return out


def _voice(settings: Settings, services: dict, voice) -> dict:
    tts = services.get("tts") or {}
    out = {"enabled": settings.voice.enabled, "engine": getattr(voice, "backend", ""),
           "voice": getattr(voice, "name", ""), "output": settings.voice.audio_output, "verified": None,
           "status": "ok", "code": "ready"}
    if not settings.voice.enabled:
        out.update(status="off", code="muted")
    elif not tts.get("ok"):
        out.update(status="warn", code="tts-missing")
    elif voice is None:
        out.update(status="warn", code="no-voice")
    return out


def _platforms(settings: Settings, sources: list[dict]) -> dict:
    enabled = [s for s in sources if s.get("enabled")]
    items = [{"platform": s.get("platform", ""), "label": s.get("label") or "", "state": (s.get("status") or {}).get("state", "")}
             for s in enabled]
    out = {"mode": settings.mode, "items": items, "status": "ok", "code": "ready"}
    if settings.mode == "demo":
        out.update(code="demo")
    elif not enabled:
        out.update(status="error", code="no-platform")
    return out


def interactions(settings: Settings, voice_ready: bool, sources: list[dict]) -> list[dict]:
    """Every behaviour ChatToon has, and whether it is on with the current settings."""
    r, sp, ctx = settings.reading, settings.spontaneous, settings.context
    spontaneous = sp.enabled and settings.mode != "assisted"
    platforms = settings.mode != "demo" and any(s.get("enabled") for s in sources)
    return [
        {"id": "answer", "on": True, "detail": settings.mode},
        {"id": "read_name", "on": voice_ready and r.mode in ("name", "name_message")},
        {"id": "read_message", "on": voice_ready and r.mode == "name_message"},
        {"id": "emotions", "on": True},
        {"id": "animations", "on": settings.animation.idle},
        {"id": "spontaneous", "on": spontaneous},
        {"id": "curiosities", "on": spontaneous and "curiosity" in sp.categories},
        {"id": "memory", "on": settings.memory.enabled, "detail": "persist" if settings.memory.persist else ""},
        {"id": "platforms", "on": platforms},
        {"id": "context", "on": bool(ctx.topic.strip() or ctx.description.strip() or ctx.channel_name.strip())},
        {"id": "voice", "on": voice_ready},
    ]


def build(settings: Settings, services: dict, service: dict, sources: list[dict], counts: dict,
          voice=None, window_open: bool = False) -> dict:
    character = get_character(settings.character)
    ai = _ai(settings, services, service)
    voice_info = _voice(settings, services, voice)
    platforms = _platforms(settings, sources)
    display = {"mode": settings.display.mode, "obs": int(counts.get("obs", 0)), "window": window_open,
               "lan": settings.overlay.lan_enabled, "remote": bool(settings.overlay.public_address),
               "status": "ok", "code": "ready"}
    if settings.display.mode in ("obs", "both") and not display["obs"]:
        display.update(status="warn", code="obs-not-connected")
    if settings.display.mode in ("window", "both") and not window_open:
        display.update(status="warn", code="window-closed")
    blocking = [x["code"] for x in (ai, platforms) if x["status"] == "error"]
    warnings = [x["code"] for x in (voice_info, display) if x["status"] in ("warn", "off")]
    return {
        "time": time.time(), "ok": not blocking, "state": "blocked" if blocking else "starting",
        "blocking": blocking, "warnings": warnings,
        "character": {"id": character.id, "name": character.name, "color": character.color,
                      "preset": settings.character_settings().personality.preset},
        "ai": ai, "voice": voice_info, "platforms": platforms, "display": display,
        "interactions": interactions(settings, voice_info["status"] == "ok", sources),
    }
