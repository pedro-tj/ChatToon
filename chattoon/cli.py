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
    sub.add_parser("doctor", help="check Ollama, TTS BigLinux and audio")
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
    engine.tts.shutdown()
    return 0 if ok and report["player"] else 1


async def _ask(text: str, character: str | None) -> int:
    from .core.brain import REPLY_SCHEMA, Brain
    from .core.characters import get_character
    from .core.config import Settings
    from .core.messages import ChatMessage
    from .core.ollama import OllamaClient, OllamaError

    s = Settings.load()
    c = get_character(character or s.character)
    cs = s.character_settings(c.id)
    brain = Brain()
    system = brain.system_prompt(c, cs.personality, s.context, s.ai.reply_language, s.ai.max_sentences, s.ai.max_chars,
                                 catchphrases=cs.catchphrases)
    async with OllamaClient(s.ai.host, s.ai.timeout) as client:
        model = s.ai.model or next(iter([m.name for m in await client.list_models()]), "")
        if not model:
            print("No Ollama model installed.", file=sys.stderr)
            return 1
        try:
            result = await client.chat(model, brain.messages(system, c, ChatMessage("cli", "You", text), s.ai.reply_language),
                                       schema=REPLY_SCHEMA, temperature=s.ai.temperature, max_tokens=s.ai.max_tokens)
        except OllamaError as e:
            print(e, file=sys.stderr)
            return 1
    reply = brain.parse(result.text, c, s.ai.reply_language, s.ai.max_sentences, s.ai.max_chars,
                        s.context.forbidden_topics)
    print(f"{c.name} [{reply.emotion}]: {reply.text}")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.WARNING,
                        format="%(levelname)s %(name)s: %(message)s")
    if args.command == "doctor":
        return asyncio.run(_doctor())
    if args.command == "ask":
        return asyncio.run(_ask(args.text, args.character))
    from .gui.app import run

    return run(sys.argv[:1])
