# Architecture

ChatToon is one desktop process: a Qt Quick interface on the main thread and an asyncio
engine on its own thread. The character is a web page (Three.js) served by the engine and
shown by OBS Studio, by a window on the desktop and by the app's own preview.

```
┌────────────────────────────── desktop process ──────────────────────────────┐
│ Qt main thread                              asyncio thread (core/runtime)    │
│ ┌──────────────┐  properties/slots ┌────────────────────────────────────────┐│
│ │ QML pages    │◄─────────────────►│ gui/backend.py + controllers           ││
│ │ (gui/qml)    │  queued signals   │   ▲ EventBus (core/events)             ││
│ └──────┬───────┘                   │ ChatToonEngine (core/engine)           ││
│        │ QtWebEngine               │  ├ MultiStreamManager (core/streams)   ││
│        ▼                           │  ├ MessageSelector (core/messages)     ││
│ overlay page: preview / desktop    │  ├ Brain + intent + memory + emotion   ││
│                                    │  ├ OllamaClient ─────► Ollama           ││
│                                    │  ├ BigLinuxTTS ──────► TTS BigLinux     ││
│                                    │  ├ AudioPlayer (pw-play/paplay/aplay)   ││
│                                    │  └ OverlayServer (aiohttp)              ││
│                                    └──────────────┬─────────────────────────┘│
└───────────────────────────────────────────────────┼──────────────────────────┘
          127.0.0.1:<port>/o/<token>/  (HTTP + WebSocket, events only)
                                                    ▼
                                    OBS Browser Source (role=obs)
```

## Rules that hold everywhere

* **Nothing slow on the GUI thread.** The engine owns the network, the model, the voice and
  every system command. The GUI calls it with `Runtime.submit()` / `call_soon_threadsafe()` and
  receives events through queued Qt signals. Blocking work (synthesis, `pacman`, `systemctl`,
  `ip`, D-Bus keyring calls) runs in `asyncio.to_thread`.
* **One answer at a time, one voice at a time.** The worker takes one message; the reading
  and the reply are spoken under `_speech_lock`. Audio is played in exactly one place: the
  desktop player, or the newest OBS source (`OverlayServer._audio_sink`). Previews, plain
  browser tabs and the desktop window watch but never get the audio.
* **Viewer text is data.** It is cleaned, length-limited, delimited in the prompt, shown with
  `Text.PlainText` / `textContent`, and never reaches a shell.
* **Codes, not sentences.** The core reports stable codes (`ai-timeout`, `pusher-outdated`,
  `no-chat-model`…); the interface turns them into translated text.

## Modules

| Area | Module |
|---|---|
| Controller (states `stopped/running/paused/emergency`, phases `idle/listening/reading/thinking/speaking`) | `core/engine.py` |
| Settings (dataclasses, tolerant load, atomic 0600 save, `config_version`, profiles) | `core/config.py` |
| Streaming connectors, manager, link recognition | `core/streams/` (see [PLATFORMS.md](PLATFORMS.md)) |
| Message queue, selection, fairness | `core/messages.py` |
| Prompt, validation, intents, memory, emotions, knowledge, spontaneous lines, context assistant | `core/brain.py`, `intent.py`, `memory.py`, `emotion.py`, `knowledge.py`, `spontaneous.py`, `assistant.py` (see [INTELLIGENCE.md](INTELLIGENCE.md)) |
| Ollama API client (streaming chat, catalog with capabilities, `/api/ps`, pull) | `core/ollama.py` |
| Ollama on this computer (package, systemd units, own `ollama serve`, install) | `core/ollama_service.py` |
| Voice through TTS BigLinux (synthesis, WAV normalisation, lip-sync envelope, player) | `core/tts.py` |
| Voice engines state and installation (reuses TTS BigLinux's modules) | `core/tts_manager.py` |
| Overlay HTTP/WebSocket server | `core/overlay_server.py` |
| System commands, packages, services | `core/system.py` |
| Network interfaces, firewall, public IP (on request) | `core/network.py` |
| Internet access check (DNS → port → TLS → proxy → WebSocket) | `core/remote_check.py` |
| Masking for the screen | `core/privacy.py`, `gui/qml/Privacy.qml` |
| Start report | `core/readiness.py` |
| Credentials (Secret Service or 0600 file) and log redaction | `core/credentials.py` |
| Hardware facts for model suggestions | `core/hardware.py` |
| CLI (`gui`, `doctor`, `ask`, `extras`, `--version`) | `cli.py` |

## Interface

`gui/backend.py` is the bridge QML talks to. Features live in small controllers, each a
`QObject` reached as `backend.<name>` (`gui/controller.py` gives them `submit()` on the engine
loop and `later()` / `_set()` back on the GUI thread):

| Controller | QML | Role |
|---|---|---|
| `aiCenter` (`ai_center.py`) | `OllamaPanel`, `ModelCatalog`, `ModelSuggestions` | Ollama state, install, start/stop, catalog, downloads |
| `voiceCenter` (`voice_center.py`) | `EngineCards` | engines, installation plans, Kokoro voices |
| `connectivity` (`connectivity.py`) | `ObsAccess`, `RemoteWizard` | local network listener, firewall, public IP, remote check, token |
| `sessionReport` (`session_report.py`) | `StartReport` | Start → checks → start → proof that AI and voice work |
| `characterWindow` (`character_window.py`) | `CharacterWindow`, `CharacterMenu`, `CharacterWindowCard` | the character on the desktop |

Pages other than the Dashboard are built on their first visit (`LazyPage` in `Main.qml`);
the two pages with a 3D preview are unloaded when left, so only one renderer runs. The
first-run wizard and the start report exist only when shown.

## Ollama on this computer (`core/ollama_service.py`)

States are told apart, never guessed from one failed request: `not_installed` (no binary and
no package), `stopped` (installed, the API does not answer), `starting` (up to 40 s waiting for
a real answer), `running`, `error` (the systemd unit failed) and `remote` (the host is another
computer: only its API is used). Who runs it: the system unit (`ollama.service`, models in
`/var/lib/ollama`), a user unit (models in `~/.ollama`), an `ollama serve` started by ChatToon
(127.0.0.1 only, stopped with the app) or another program (Alpaca, a terminal, Docker), which
ChatToon never stops. Other Ollama servers on known local ports (11434, 11435 for Alpaca) are
reported, because their models live elsewhere — the usual reason for "my models are missing".

Install: base package `ollama` plus an optional acceleration add-on (`ollama-vulkan` for AMD and
Intel, `ollama-cuda` for NVIDIA, `ollama-rocm` on request), with sizes from `pacman -Si`.
Models come from `/api/tags` and each one's `/api/show` capabilities (`completion`, `vision`,
`tools`, `thinking`, `embedding`); `/api/ps` tells which are loaded. Models that cannot chat are
listed with the reason; a chosen model that disappears is reported and blocks Start, never
replaced. Downloads report real progress per layer, speed and can be cancelled (Ollama keeps
the parts). Before downloading, the exact size is read from the registry manifest.

## Voice engines (`core/tts_manager.py`)

Each engine is `not_installed`, `needs_voice` (the program exists but has no voice in the reply
language), `ready` or `error`, from TTS BigLinux's own `voice_manager`. Installation reuses TTS
BigLinux's `package_installer` (repository first, both package spellings, AUR only through
pamac/paru/yay as the user) and Kokoro voices come from its `kokoro_voice_service`. ChatToon only
installs `tts-biglinux` itself when it is missing. Packages: Piper `piper-tts-bin` +
`piper-voices-pt-BR`; Kokoro `biglinux-kokoro-tts`; RHVoice `rhvoice` + `rhvoice-voice-leticia-f123`;
espeak-ng `espeak-ng`.

## Start report (`core/readiness.py`, `gui/session_report.py`)

Start refreshes the services, builds a report of facts (codes) and starts only if nothing
essential is missing: Ollama answering with a chat model installed and chosen, and an enabled
platform outside Demo mode. Voice and display issues are warnings. After starting, the model is
loaded and a silent "Oi!" is rendered with the character's voice; the report then says how long
the model took and whether the voice works. It also lists which behaviours are on.

## Overlay protocol

The page (`web/overlay/overlay.js`) joins `ws://…/o/<token>/ws?role=<role>`:

| Role | Who | Audio | Notes |
|---|---|---|---|
| `obs` | OBS Browser Source (detected by `window.obsstudio`) | the newest one plays it | default |
| `browser` | the same link in a normal browser tab | never | so checking the link does not take the voice from OBS |
| `preview` | the app's previews | never | 30 fps cap |
| `desktop` | the character window | never | frames the character itself (`frameDesktop`) |
| `probe` | the internet check | — | gets `{"type": "hello"}` and is closed, never counted |

Server → page events: `config`, `state`, `speak` (text, emotion, intensity, optional `lead`
and `gesture`, envelope, audio URL for the sink only), `done`, `stop`, `react`, `gesture`.
Page → server: only `ended` (from the audio sink). Anything else is ignored: the page has no
authority over the app.

## The character window

`CharacterWindow.qml` is a frameless transparent `Window` holding a `WebEngineView` with the
overlay page in role `desktop`. On X11 the usual window flags apply; on KDE Plasma (Wayland
and X11) `gui/kwin.py` loads a small KWin script over D-Bus that keeps the window above, keeps
it out of the taskbar when asked, places it (first time: the bottom-right corner of the usable
area) and reports its geometry back so the position survives a restart. Capabilities are
detected, never assumed; without KWin on Wayland, keep-above and position are reported as
unavailable. Clicks pass through the transparent area thanks to an input mask; the
"clicks pass through" option makes the whole window input-transparent. The window never plays
sound.

Two QtWebEngine details matter: a window created with `QQmlComponent` needs C++ ownership or
the QML garbage collector deletes it; and in a transparent window, layers promoted with
`will-change: opacity` are blended with the wrong alpha, so the desktop bubble is opaque and
never promoted.

## Network exposure

| Listener | Address | Who is answered |
|---|---|---|
| Overlay | `127.0.0.1:<port>` (8765 or the next free port) | `Host` must be loopback, or the one public HTTPS host configured for a reverse proxy |
| Overlay, local network (opt-in) | one private IPv4 of this computer, same port | `Host` must be that IP and the caller must be in its subnet |
| Kick webhooks (opt-in) | `127.0.0.1:<kick_webhook_port>` | RSA-signed requests only |

Ollama and the app's controls are never exposed. See [SECURITY.md](SECURITY.md).

## Settings and data

| Path | Content |
|---|---|
| `~/.config/chattoon/settings.json` | settings (0600). `config_version` 3; a 2.x file is copied once to `settings.json.v2.bak` |
| `~/.config/chattoon/profiles/*.json` | stream profiles (no secrets, no local network data) |
| Secret Service (`org.biglinux.ChatToon`) or `~/.local/share/chattoon/credentials.json` (0600) | logins and tokens |
| `~/.local/share/chattoon/memory.sqlite3` (0600) | memories between lives, only when enabled |
| `~/.local/share/chattoon/extras/` | optional TikTokLive venv |
| `~/.cache/chattoon/ollama-serve.log` (0600) | output of an `ollama serve` started by ChatToon |
| `$TMPDIR/chattoon-tts-*/` (0700) | the last rendered replies, removed on exit |

## Measured (2026-10-17, Ryzen 7 5700G, RX 9060 XT, KDE Plasma 6 Wayland)

Same isolated profile, Dashboard with the 3D preview, main process plus QtWebEngine helpers:

| | 2.3.0 | 3.0.0 |
|---|---|---|
| First frame after launch | 1.96 s | 1.72 s |
| QML load | 0.33 s | 0.16 s |
| Memory (USS, all processes) | 523 MB | 482 MB |
| Idle CPU on the Dashboard | 18 % | 9.5 % |
| Idle CPU on a page without preview | 0.1 % | 0.1 % |

Reply and voice latency are in [INTELLIGENCE.md](INTELLIGENCE.md).
