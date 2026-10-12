# 10 — Testing

```bash
python -m venv --system-site-packages .venv && .venv/bin/pip install pytest
.venv/bin/python -m pytest              # offline suite (~10 s)
.venv/bin/python -m pytest --run-live   # + real Ollama, TTS BigLinux (incl. Kokoro) and (with CHATTOON_LIVE_URL) a live chat
CHATTOON_TEST_CHARACTERS=tux,cat .venv/bin/python -m pytest tests/test_overlay_render.py   # browser tests for some characters
```

The browser tests need Chrome or Chromium (`CHATTOON_BROWSER=/path/to/chrome` picks one) and
use software WebGL, so they are slow (~2–3 min); they are skipped when no browser is found.

Tests isolate `XDG_*` directories, use local fake servers for Ollama and YouTube, and run the
interface offscreen with software rendering.

| File | Covers |
|---|---|
| `test_messages_config.py` | settings round-trip/garbage/permissions, profiles, text cleaning, dedup, spam, modes, cooldown, TTL, queue limit, starvation |
| `test_youtube_chat.py` | every URL form, parsing (badges, Super Chat, emoji), backlog, reconnect, end, disabled chat, cancel; live test |
| `test_ollama_brain.py` | streaming, options, `think`, errors, unavailable service, timeout, cancel; prompts, injection wrapping, stable system prompt, reply cleaning, limits, fallbacks, calls to action; live test |
| `test_tts_overlay.py` | envelope, missing package, stdin-only, single player; overlay routes/CSP/traversal/DNS rebinding/loopback, single audio sink, read-only WebSocket; live synthesis |
| `test_engine.py` | demo flow with exactly one voice per reply, AI failure, assisted approval, emergency stop, pause, URL requirement, manual say/react/muted, overlay audio, character switch, reply length, background |
| `test_gui.py` | backend bridge, settings paths and persistence, profiles, demo flow through the GUI (reading + reply), every QML page loads without warnings, wizard, icons, no hard-coded Portuguese, WCAG contrast, six characters with gestures and thumbnails, animation/reading settings reaching the overlay, error messages in the interface language, gesture name validation, card click vs. expand button |
| `test_i18n.py` | translation complete, every `qsTr` in the catalogue, `.qm` up to date, plural forms |
| `test_packaging.py` | package data, PKGBUILD, desktop file, icon, Three.js checksums, no shell/secrets |
| `test_kokoro.py` | Kokoro through a fake `koko` (real subprocesses): `koko text` only (never a playing mode), voice/speed/argv/cwd, PCM16 conversion and envelope, unavailable voice/model, engine failure with filtered stderr, invalid WAV, cancel kills and reaps, cancel drops queued renders, timeout, engine that cannot start, WAV formats (8/16/24-bit PCM, float, extensible, streaming header), gain without clipping; live: real `pf_dora`/`pm_alex` |
| `test_reading.py` | speakable names/messages, templates (said/asked/Super Chat/name only/English), cutting without rewriting, emoji/link-only messages, settings default and migration, reading → reply order with one voice at a time, name-only, off, generation overlapping the reading, interrupt/emergency/pause during the reading, blocked and forbidden messages, separate reading voice, assisted (read only after approval) and automatic modes, TTS failure on the reading, character switch, AI failure, Kokoro lines voiced sentence by sentence (order, groups, progress), interrupt between segments |
| `test_overlay_render.py` | the real overlay in headless Chrome/Chromium (skipped without one): six characters × two qualities load, every gesture and reaction runs without JS errors, draw-call/triangle budgets; OBS page stays transparent while moving (corners, top edge never cut), chroma key; reading bubble → waiting dots → reply swap, never covering the face; GPU resources stable over repeated switches; idle never frozen; reduced motion skips big gestures; mouth moves only with real audio |

## Results 2.1.0 (2026-10-11)

- Offline suite: **164 passed**, 5 live tests skipped; the six browser tests ran with
  Chrome 'headless=new' + SwiftShader over all six characters.
- Live: real Kokoro `pf_dora`/`pm_alex`, real TTS BigLinux and real Ollama
  (`CHATTOON_LIVE_MODEL=llama3.1:8b`) pass. With `smallthinker` the Ollama live test fails
  (the model returns an empty answer to the full prompt).
- Real end-to-end runs (Ollama + Kokoro + `pw-play`, and the OBS audio path in Chromium):
  see [12-character-tts-upgrade.md §4](12-character-tts-upgrade.md).

## Results 2.0.0 (2026-10-11)

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
