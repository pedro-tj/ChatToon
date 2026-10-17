"""Voice engines of TTS BigLinux: what is installed, what is missing, and installing it
(docs/32-tts-engine-management.md).

ChatToon does not keep its own engine or voice manager. Everything reuses TTS BigLinux:
``voice_manager`` decides whether an engine is installed and has voices, its
``package_installer`` checks the repositories and installs (``pkexec pacman -S --needed``,
AUR only through pamac/paru/yay as the person), and ``kokoro_voice_service`` downloads
Kokoro voices. Only TTS BigLinux itself — when it is missing — is installed by ChatToon.

Every function blocks: call it from a worker thread.
"""

from __future__ import annotations

import logging

from .tts import BigLinuxTTS, TTSError, Voice

log = logging.getLogger(__name__)

TTS_BIGLINUX_PACKAGE = "tts-biglinux"
ENGINES = ("piper", "kokoro", "rhvoice", "espeak-ng")
LABELS = {"rhvoice": "RHVoice", "espeak-ng": "espeak-ng", "piper": "Piper", "kokoro": "Kokoro"}
# The program of each engine (TTS BigLinux spells them like this) …
ENGINE_PACKAGES = {"rhvoice": ["rhvoice"], "espeak-ng": ["espeak-ng"], "piper": ["piper-tts-bin"],
                   "kokoro": ["biglinux-kokoro-tts"]}
# … and a first voice in the reply language. Spelling differs between BigLinux stable and
# testing (piper-voices-pt-br / piper-voices-pt-BR): package_installer.resolve tries both.
VOICE_PACKAGES = {
    "rhvoice": {"pt": "rhvoice-voice-leticia-f123", "en": "rhvoice-voice-clb"},
    "piper": {"pt": "piper-voices-pt-BR", "en": "piper-voices-en-US", "es": "piper-voices-es-ES"},
}
_STATE = {"not-installed": "not_installed", "no-voices": "needs_voice", "ready": "ready"}


def _lang(language: str) -> str:
    return (language or "pt").lower().split("-")[0]


def states(tts: BigLinuxTTS, language: str) -> dict:
    """Real state of every engine: not_installed | needs_voice | ready | error.

    "ready" means a voice in the reply language exists, not just the program: an engine with
    only English voices "needs a voice" for a Portuguese stream. Refreshes the voice cache."""
    if not tts.available:
        return {"installed": False, "error": tts.error or "TTS BigLinux is not installed",
                "engines": {e: {"state": "unavailable", "voices": 0, "inLanguage": 0, "label": LABELS[e]}
                            for e in ENGINES}}
    vm = tts._load()[0]
    try:
        catalog = vm.discover_voices()
        available = vm.engine_availability(catalog)
    except Exception as e:  # noqa: BLE001 - a broken engine must not break the page
        log.warning("voice discovery failed: %s", e)
        return {"installed": True, "error": str(e)[:200], "engines": {
            e: {"state": "error", "voices": 0, "inLanguage": 0, "label": LABELS[e]} for e in ENGINES}}
    lang = _lang(language)
    usable = {k for k, v in available.items() if getattr(v, "value", v) == "ready"}
    tts._voices = [Voice(v.voice_id, v.name, v.language, v.backend, v.gender or "", v.quality or "")
                   for v in catalog.voices if v.backend in usable]
    engines = {}
    for engine in ENGINES:
        voices = catalog.get_by_backend(engine)
        in_lang = [v for v in voices if _lang(v.language) == lang]
        raw = getattr(available.get(engine), "value", available.get(engine, "not-installed"))
        state = _STATE.get(raw, "error")
        if state == "ready" and not in_lang:
            state = "needs_voice"
        engines[engine] = {"state": state, "voices": len(voices), "inLanguage": len(in_lang), "label": LABELS[engine],
                           "voicePackage": VOICE_PACKAGES.get(engine, {}).get(lang, ""),
                           "downloadable": engine == "kokoro"}
    return {"installed": True, "error": "", "engines": engines}


def _installer(tts: BigLinuxTTS):
    tts._load()
    from services import package_installer  # type: ignore[import-not-found]

    return package_installer


def plan(tts: BigLinuxTTS, engine: str, language: str) -> dict:
    """Which packages would be installed for ``engine`` and where they come from
    (installed | repo | aur | "" = nowhere). Nothing is installed here."""
    if engine == TTS_BIGLINUX_PACKAGE or not tts.available:
        from . import system

        info = system.package_info(TTS_BIGLINUX_PACKAGE)
        source = "installed" if info.installed else "repo" if info.available else ""
        return {"engine": TTS_BIGLINUX_PACKAGE, "items": [{"wanted": TTS_BIGLINUX_PACKAGE, "name": TTS_BIGLINUX_PACKAGE,
                                                           "source": source, "size": info.download_size}]}
    if engine not in ENGINES:
        return {"engine": engine, "items": []}
    wanted = list(ENGINE_PACKAGES[engine])
    voice = VOICE_PACKAGES.get(engine, {}).get(_lang(language))
    if voice:
        wanted.append(voice)
    try:
        resolved = _installer(tts).resolve(wanted)
    except Exception as e:  # noqa: BLE001 - shown as "could not check"
        return {"engine": engine, "items": [], "error": str(e)[:200]}
    items = []
    for r in resolved:
        size = ""
        if r.source == "repo":
            try:
                size = _installer(tts).query(r.name).download_size
            except Exception:  # noqa: BLE001
                size = ""
        items.append({"wanted": r.wanted, "name": r.name, "source": r.source, "size": size})
    return {"engine": engine, "items": items}


def install(tts: BigLinuxTTS, engine: str, items: list[dict]) -> dict:
    """Install a plan made by :func:`plan` (repository packages first, then the AUR)."""
    if engine == TTS_BIGLINUX_PACKAGE:
        raise ValueError("tts-biglinux is installed through chattoon.core.system")
    pi = _installer(tts)
    allowed = set(ENGINE_PACKAGES.get(engine, [])) | {v.lower() for v in VOICE_PACKAGES.get(engine, {}).values()}
    repo = [i["name"] for i in items if i.get("source") == "repo"]
    aur = [i["name"] for i in items if i.get("source") == "aur"]
    if any(n.lower() not in {a.lower() for a in allowed} for n in repo + aur):
        return {"ok": False, "message": "", "detail": "unexpected package", "code": "invalid"}
    result = pi.install(repo) if repo else pi.InstallResult(True)
    if result.ok and aur:
        result = pi.install_aur(aur)
    tts.voices(refresh=True) if result.ok else None
    return {"ok": bool(result.ok), "message": result.message, "detail": result.detail, "code": "" if result.ok else "failed"}


# -- Kokoro voices (downloaded by TTS BigLinux) -------------------------------------------

def kokoro_voices(tts: BigLinuxTTS) -> list[dict]:
    try:
        tts._load()
        from services import kokoro_voice_service as kvs  # type: ignore[import-not-found]
    except (TTSError, ImportError):
        return []
    try:
        rows = kvs.get_voice_status()
    except Exception as e:  # noqa: BLE001
        log.warning("Kokoro voice list failed: %s", e)
        return []
    return [{"id": r["voice_id"], "name": r["display_name"], "language": r["language"], "gender": r.get("gender", ""),
             "installed": r["installed"] == "yes", "base": r.get("is_base") == "yes",
             "description": r.get("description", "")} for r in rows]


def download_kokoro(tts: BigLinuxTTS, voice_id: str, progress=None, cancelled=None) -> tuple[bool, str]:
    tts._load()
    from services import kokoro_voice_service as kvs  # type: ignore[import-not-found]

    ok, error = kvs.download_voice(voice_id, progress_cb=progress, cancel_check=cancelled)
    if ok:
        tts.voices(refresh=True)
    return ok, error
