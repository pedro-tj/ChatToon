# ChatToon

**A 3D character that joins your YouTube live stream:** it reads the chat, answers with its
own sense of humour using a local AI (Ollama), speaks with a real voice (TTS BigLinux) and
animates in sync with the speech — on an OBS overlay with a transparent background.
Everything except the YouTube chat runs on your computer.

![The cast: Minhoca, E.T. and Tux](docs/screenshots/cast.png)

| Dashboard | Characters |
|---|---|
| ![Dashboard](docs/screenshots/dashboard.png) | ![Characters](docs/screenshots/characters.png) |
| **Speaking (bubble follows the voice)** | **Portuguese, dark theme** |
| ![Speaking](docs/screenshots/speaking.png) | ![Dashboard in Portuguese](docs/screenshots/dashboard-pt-dark.png) |

## Features

- **Three original procedural 3D characters** (Three.js, no downloads, no third-party
  assets): **Minhoca**, a cheeky skinned worm popping out of the dirt; **E.T.**, a levitating
  alien with spring antennae; **Tux**, a geek penguin with an articulated beak. Expressions
  (happy, laugh, surprised, confused, annoyed, celebrate, thinking), blinking, gaze,
  gestures and **lip sync from the real audio envelope**.
- **Local AI personality engine**: presets (Friendly, Comedian, Teaser, Geek, Controlled
  chaos, Custom), nine humour dials, channel context, real clock awareness, short-term
  memory, catchphrases and occasional calls to action. Viewer messages are treated as data,
  never as instructions.
- **YouTube Live chat** from a pasted link (watch, live, youtu.be, live_chat, pop-out): no
  login, de-duplication by message id, reconnect with backoff, end-of-stream detection.
- **Message selection**: smart, all, mentions, questions, moderators, members, random or
  manual; per-viewer cooldown, expiry, queue limit, blocked words, Super Chat priority.
- **Three modes**: Demo (no YouTube needed), Assisted (you approve each suggestion) and
  Automatic.
- **One voice per reply, always**: TTS BigLinux voices (Piper, RHVoice, espeak-ng) rendered
  once and played either by the app or by the OBS source — never both.
- **OBS overlay** at a local secret URL: transparent or chroma-key background, speech bubble,
  size/position/camera/light/quality/FPS controls, live preview inside the app.
- **Live controls**: start, pause, stop, interrupt, mute, clear queue, make it say a phrase,
  trigger reactions, and an **emergency stop** that silences everything at once.
- Light/dark/system theme, keyboard shortcuts, first-run assistant, English interface with a
  complete Brazilian Portuguese translation, stream profiles (export without secrets).

## Install (BigLinux / Manjaro / Arch)

```bash
git clone https://github.com/ruscher/ChatToon.git
cd ChatToon/packaging/arch
makepkg -si
```

Then open **ChatToon** from the menu (or run `chattoon`). Remove with `sudo pacman -R chattoon`.

Dependencies: `python`, `pyside6`, `python-aiohttp`, `qt6-svg`, `qt6-webengine`.
Optional: `tts-biglinux` (voice, BigLinux repository), `ollama` (AI — or a remote Ollama),
`pipewire-audio`/`pulseaudio-utils`/`alsa-utils` (desktop audio), `obs-studio`.

Run from the source tree without installing:

```bash
sudo pacman -S --needed pyside6 python-aiohttp qt6-svg qt6-webengine
python -m chattoon            # desktop app
python -m chattoon doctor     # checks Ollama, TTS BigLinux and audio
python -m chattoon ask "Meu Windows travou!" --character tux
```

### Ollama

ChatToon uses the Ollama already installed on the machine (BigLinux Settings can install it)
and never changes its configuration. Pick any installed chat model on the
**Artificial intelligence** page, or download a suggested one from there (with progress).
`gemma3:4b` (3.3 GB) is the default suggestion: good Brazilian Portuguese at about 20
tokens/s on a GTX 1050 Ti. See [docs/04-ollama.md](docs/04-ollama.md) for latency notes.

### TTS BigLinux

Install `tts-biglinux`. ChatToon imports its voice catalog, text normalisation and native
synthesizer, so every voice you installed for TTS BigLinux is available. Each character can
have its own voice, speed and pitch (**Voice** page, with preview).

## Using it

1. **First run**: the assistant checks Ollama and the voice and lets you pick a character.
2. **Try it** in **Demo** mode: type on the Dashboard as if you were a viewer.
3. **YouTube chat** page: paste the live link; choose how messages are selected.
4. **Stream context** page: channel, topic, guests, forbidden topics, calls to action.
5. **OBS Studio** page: copy the overlay address → in OBS add a **Browser** source with that
   URL, 1920×1080. If the voice should come from OBS, choose *Inside OBS* on the Voice page and
   enable *Control audio via OBS* on the source.
6. Switch to **Assisted** or **Automatic** and press **Start** (`Ctrl+Space`).

Shortcuts: `Ctrl+Space` start/pause · `Ctrl+.` interrupt · `Ctrl+M` mute ·
`Ctrl+Shift+X` or `Pause` emergency stop · `Ctrl+1…9` pages.

## Troubleshooting

| Problem | What to do |
|---|---|
| Ollama "Not running" | `sudo systemctl start ollama` (or install it in BigLinux Settings), then *Check again* |
| No model | Download a suggested model on the AI page |
| Voice "Unavailable" | `sudo pacman -S tts-biglinux` |
| Chat "unavailable"/"disabled" | The stream is not live, the chat is off or members-only; the message says which |
| OBS shows nothing | The app must be open; check the URL; leave *Shutdown source when not visible* off |
| Voice twice | Cannot happen by design; if you hear an echo, OBS is capturing Desktop Audio *and* the source |
| Slow replies | Lower *Conversation memory*, use a smaller model, keep only one model loaded |

## Documentation

[Audit](docs/01-audit.md) · [Architecture](docs/02-architecture.md) · [UI/UX](docs/03-ui-ux.md) ·
[Ollama](docs/04-ollama.md) · [YouTube](docs/05-youtube.md) · [TTS](docs/06-tts.md) ·
[Avatars](docs/07-avatars.md) · [OBS](docs/08-obs.md) · [Security](docs/09-security.md) ·
[Testing](docs/10-testing.md) · [Release](docs/11-release.md)

## License and credits

ChatToon is GPL-3.0-or-later.

- [Three.js](https://threejs.org) 0.186.1 — MIT, vendored in `chattoon/web/vendor/three`.
- Interface icons in the style of [Lucide](https://lucide.dev) — ISC.
- The penguin is an original procedural model inspired by **Tux**, created by Larry Ewing
  (lewing@isc.tamu.edu) with The GIMP.
- Voices and text processing by [TTS BigLinux](https://github.com/biglinux/tts-biglinux);
  AI by [Ollama](https://ollama.com).
- Original prototype: the scripts in `legacy/` (see their README).
