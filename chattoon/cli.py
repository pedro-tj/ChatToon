"""Command line entry point. Without arguments it opens the desktop app."""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys

from . import __version__


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="chattoon", description="Virtual 3D co-host for live streams (local AI).")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    p.add_argument("-v", "--verbose", action="store_true", help="debug logging")
    sub = p.add_subparsers(dest="command")
    sub.add_parser("gui", help="open the desktop app (default)")
    sub.add_parser("doctor", help="check Ollama, TTS BigLinux, audio and streaming platforms")
    extras = sub.add_parser("extras", help="optional components (installed in a private folder)")
    extras.add_argument("action", choices=["install", "status"])
    extras.add_argument("name", choices=["tiktok"])
    say = sub.add_parser("ask", help="ask the current character something (prints, does not speak)")
    say.add_argument("text")
    say.add_argument("--character", choices=["worm", "alien", "tux", "cat", "owl", "dog"])
    return p


async def _doctor() -> int:
    from .core.config import Settings
    from .core.engine import ChatToonEngine

    settings = Settings.load()
    engine = ChatToonEngine(settings)
    report = await engine.check_services()
    await engine.ollama.close()
    ok = True
    o = report["ollama"]
    if o.get("ok"):
        print(f"✔ Ollama {o['version']} — models: {', '.join(o['models']) or 'none (download one in the app)'}")
    else:
        ok = False
        print(f"✘ Ollama: {o.get('error')}")
    t = report["tts"]
    if t.get("ok"):
        pt = [v["name"] for v in t["voices"] if v["language"].lower().startswith("pt")]
        print(f"✔ TTS BigLinux — {len(t['voices'])} voices ({len(pt)} in Portuguese)")
        names = {"rhvoice": "RHVoice", "espeak-ng": "espeak-ng", "piper": "Piper", "kokoro": "Kokoro"}
        for engine_id, label in names.items():
            count = sum(v["backend"] == engine_id for v in t["voices"])
            print(f"  ✔ {label}: {count} voice(s)" if count else f"  · {label}: not installed")
    else:
        ok = False
        print(f"✘ TTS BigLinux: {t.get('error')}")
    print("✔ audio player found" if report["player"] else "✘ no audio player (install pipewire or alsa-utils)")
    m, sp = settings.memory, settings.spontaneous
    print(("✔ conversation memory on" if m.enabled else "· conversation memory off")
          + (f" · saved between lives for {m.retention_days or '∞'} day(s)" if m.enabled and m.persist else
             " · not saved between lives" if m.enabled else ""))
    print("✔ spontaneous lines on" if sp.enabled else "· spontaneous lines off")
    engine.tts.shutdown()
    _doctor_streams(settings)
    return 0 if ok and report["player"] else 1


def _doctor_streams(settings) -> None:
    """Configured platforms, keyring and optional components (never prints secrets)."""
    import importlib.util

    from .core import extras
    from .core.credentials import open_store
    from .core.streams import PLATFORMS

    store = open_store()
    print("✔ logins in the system keyring" if store.encrypted else "· no keyring found: logins kept in a private file")
    extras.activate()
    has_tiktok = importlib.util.find_spec("TikTokLive") is not None
    print("✔ TikTokLive installed" if has_tiktok else "· TikTok support not installed (chattoon extras install tiktok)")
    sources = settings.stream_sources()
    if not sources:
        print("· no streaming platform configured")
    for s in sources:
        info = PLATFORMS[s.platform]
        print(f"  {'✔' if s.enabled else '·'} {info['label']} ({info['support']}): {s.label or s.target}")


async def _ask(text: str, character: str | None) -> int:
    """One reply through the same pipeline as the live (intent, exact math, memory,
    validation, emotion) — printed, never spoken, and never remembered."""
    from .core.config import Settings
    from .core.engine import ChatToonEngine
    from .core.messages import ChatMessage

    s = Settings.load()
    if character:
        s.character = character
    s.memory.persist = False  # a question typed in the terminal is nobody's memory
    engine = ChatToonEngine(s)
    try:
        if not s.ai.model:
            models = [m.name for m in await engine.ollama.list_models()]
            if not models:
                print("No Ollama model installed.", file=sys.stderr)
                return 1
            s.ai.model = models[0]
        errors = []
        engine.bus.subscribe(lambda kind, data: errors.append(data.get("message", "")) if kind == "error" else None)
        reply = await engine.generate(ChatMessage("cli", "You", text, platform="manual"), announce=False)
        if reply is None:
            print(errors[-1] if errors else "No reply.", file=sys.stderr)
            return 1
        d = reply.diagnostics
        print(f"{engine.character.name} [{reply.emotion}{'←' + reply.lead if reply.lead else ''}]: {reply.text}")
        print(f"  ({d.get('intent')}, temperature {d.get('temperature')}, {d.get('seconds')} s"
              + (", exact result" if reply.source == "tool" else "") + (", retried" if reply.retries else "") + ")",
              file=sys.stderr)
        return 0
    finally:
        await engine.ollama.close()
        engine.close_memory()
        engine.tts.shutdown()


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.WARNING,
                        format="%(levelname)s %(name)s: %(message)s")
    from .core.credentials import install_log_redaction

    install_log_redaction()  # tokens never reach a log line, even with --verbose
    if args.command == "doctor":
        return asyncio.run(_doctor())
    if args.command == "ask":
        return asyncio.run(_ask(args.text, args.character))
    if args.command == "extras":
        import importlib.util

        from .core import extras

        if args.action == "install":
            print("Installing into", extras.venv_dir(), "(nothing outside this folder changes)")
            return extras.install(args.name)
        installed = extras.activate() and importlib.util.find_spec("TikTokLive") is not None
        print("installed" if installed else "not installed")
        return 0 if installed else 1
    from .gui.app import run

    return run(sys.argv[:1])
