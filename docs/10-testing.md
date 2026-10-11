# 10 — Testing

```bash
python -m venv --system-site-packages .venv && .venv/bin/pip install pytest
.venv/bin/python -m pytest              # offline suite (~10 s)
.venv/bin/python -m pytest --run-live   # + real Ollama, TTS BigLinux and (with CHATTOON_LIVE_URL) a live chat
```

Tests isolate `XDG_*` directories, use local fake servers for Ollama and YouTube, and run the
interface offscreen with software rendering.

| File | Covers |
|---|---|
| `test_messages_config.py` | settings round-trip/garbage/permissions, profiles, text cleaning, dedup, spam, modes, cooldown, TTL, queue limit, starvation |
| `test_youtube_chat.py` | every URL form, parsing (badges, Super Chat, emoji), backlog, reconnect, end, disabled chat, cancel; live test |
| `test_ollama_brain.py` | streaming, options, `think`, errors, unavailable service, timeout, cancel; prompts, injection wrapping, stable system prompt, reply cleaning, limits, fallbacks, calls to action; live test |
| `test_tts_overlay.py` | envelope, missing package, stdin-only, single player; overlay routes/CSP/traversal/DNS rebinding/loopback, single audio sink, read-only WebSocket; live synthesis |
| `test_engine.py` | demo flow with exactly one voice per reply, AI failure, assisted approval, emergency stop, pause, URL requirement, manual say/react/muted, overlay audio, character switch, reply length, background |
| `test_gui.py` | backend bridge, settings paths and persistence, profiles, demo flow through the GUI, every QML page loads without warnings, wizard, icons, no hard-coded Portuguese, WCAG contrast |
| `test_i18n.py` | translation complete, every `qsTr` in the catalogue, `.qm` up to date, plural forms |
| `test_packaging.py` | package data, PKGBUILD, desktop file, icon, Three.js checksums, no shell/secrets |

## Results (2026-10-11)

- Offline suite: **all passing** (see `git log` for the count at each commit); 3 live tests
  skipped by default.
- Live tests run on this machine: real Ollama reply, real TTS BigLinux synthesis, real YouTube
  live chat (9 messages / 25 s) — passing.

## Full flow (manual + scripted, real services)

Dashboard → Demo → message → Ollama (`gemma3:4b`) → TTS BigLinux → overlay animation and
bubble → stop → switch to E.T. → repeat → switch to Tux → repeat: **done**, one audio per
reply, zero QML warnings. Audio was rendered for real but played through a silent player
(night-time session), so actual speaker output and OBS capture were **not** verified by ear.

## Long-session evidence

- Overlay: 400 speeches + 57 character switches — found and fixed a GPU texture leak; after
  the fix resources stay flat (see `07-avatars.md`).
- Engine: 1 200 simulated messages through the full pipeline with fast fakes; memory samples
  in `11-release.md`.

## Not covered automatically

OBS itself (no OBS automation), audio heard on speakers, YouTube Super Chats/members on a real
stream (parsing is unit-tested with documented structures), multi-monitor behaviour.
