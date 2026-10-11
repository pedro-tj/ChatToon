# 02 — Architecture

```
┌──────────────────────── desktop process ─────────────────────────┐
│  Qt main thread                     asyncio thread (core/runtime) │
│  ┌──────────────┐  slots/props   ┌─────────────────────────────┐ │
│  │ QML pages    │◄──────────────►│ gui/backend.py (bridge)     │ │
│  │ (gui/qml)    │   queued Qt    │   ▲ EventBus (core/events)  │ │
│  └──────────────┘    signals     │   │                         │ │
│        │ QtWebEngine preview     │ ChatToonEngine (core/engine)│ │
│        ▼                         │  ├ LiveChatClient (youtube) │ │
│  overlay page (role=preview)     │  ├ MessageSelector          │ │
│                                  │  ├ Brain (personality)      │ │
│                                  │  ├ OllamaClient ──► Ollama  │ │
│                                  │  ├ BigLinuxTTS ──► tts-biglinux modules
│                                  │  ├ AudioPlayer (pw-play…)   │ │
│                                  │  └ OverlayServer (aiohttp)  │ │
│                                  └──────────┬──────────────────┘ │
└─────────────────────────────────────────────┼────────────────────┘
                     127.0.0.1:<port>/o/<token>/ (HTTP + WebSocket, events only)
                                              ▼
                                OBS Browser Source (role=obs)
```

## Components

| Component (spec name) | Module |
|---|---|
| Application Controller | `core/engine.py` — state machine `stopped/running/paused/emergency`, phases `idle/thinking/speaking` |
| Settings Manager | `core/config.py` — dataclasses, tolerant JSON load, atomic save (0600), profiles |
| YouTube Chat Connector | `core/youtube_chat.py` |
| Message Queue + Selection Engine | `core/messages.py` |
| AI Personality Engine | `core/brain.py` + `core/characters.py` |
| Ollama Service | `core/ollama.py` |
| TTS Service | `core/tts.py` |
| Avatar Animation Engine | `web/overlay/rig.js` + `characters/*.js` |
| OBS Overlay Server | `core/overlay_server.py` |
| Event Bus | `core/events.py` |
| History Manager | `engine.history` (bounded deque, memory only) |
| Logging and Diagnostics | `logging`, `chattoon doctor`, Settings → Diagnostics |

## Pipeline

`message → validation (clean_text, control/bidi chars, length) → filter (empty, !commands,
blocked words, duplicates, repeats, mention mode) → selection (mode, score, cooldown, TTL) →
context (system prompt + memory + live context) → Ollama (JSON schema, streaming, timeout,
cancel) → reply validation (JSON parse, Markdown/emoji/URL strip, sentence and character
limits, forbidden-topic check, safe fallback line) → optional call to action → TTS (one WAV,
loudness envelope) → speak event (overlay) + playback (one sink) → history`.

Only one answer is processed at a time (`_current` task + `_speech_lock`), so replies never
overlap and generations never compete for the GPU.

## Threads and responsiveness

The engine runs in its own asyncio loop (`core/runtime.py`). Blocking work (TTS synthesis,
waiting for the audio player) goes to `asyncio.to_thread`. The GUI calls the engine with
`run_coroutine_threadsafe`/`call_soon_threadsafe` and receives events through queued Qt
signals, so the interface never waits on the network, the model or the voice.

## Extensibility

`LiveChatClient` is injected through `chat_factory`; a Twitch or Rumble connector only needs
the same `run()`/`on_message(ChatMessage)`/`on_status(ChatStatus)` contract. `ChatMessage`
already has a `platform` field.
