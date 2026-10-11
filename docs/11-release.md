# 11 — Release 2.0.0

## Build and install

```bash
cd packaging/arch && makepkg -si
```

The PKGBUILD builds from this repository (no downloads during the build), compiles the
translation (`lrelease`), installs the wheel with `python -m installer`, the `.desktop` file,
the scalable icon, the README and the Three.js licence. Three.js is vendored with SHA-256
checksums verified by the tests. Per-user data follows XDG:

| Path | Content |
|---|---|
| `~/.config/chattoon/settings.json` | settings (mode 0600) |
| `~/.config/chattoon/profiles/*.json` | saved stream profiles (no secrets) |
| `$TMPDIR/chattoon-tts-*/` | last 20 rendered replies (0700), deleted on exit |

## Acceptance checklist

| Criterion | Status |
|---|---|
| Opens on BigLinux, GUI functional | ✅ (screenshots in `docs/screenshots`, all pages load without QML warnings) |
| Ollama detected, installed models selectable | ✅ real Ollama 0.33.3 |
| TTS BigLinux integrated, voices testable | ✅ real synthesis with Piper, RHVoice, espeak-ng; preview button |
| Three characters with working animations | ✅ Minhoca, E.T., Tux |
| YouTube URL accepted, chat read and processed | ✅ real live stream (read-only test) |
| Contextual AI replies | ✅ real replies with each character |
| Each reply spoken once | ✅ tested; real WAVs rendered |
| Avatar animates while speaking | ✅ lip sync from the audio envelope |
| Overlay works in an OBS-compatible browser | ✅ rendered in QtWebEngine (Chromium, like OBS's CEF); not tested inside OBS |
| Settings kept after restart | ✅ tested |
| Demo mode without YouTube | ✅ |
| Responsive during generation and speech | ✅ engine in its own thread |
| Service failures handled clearly | ✅ typed errors, status cards, fixes shown |
| Tests and documentation | ✅ |
| PKGBUILD validated | ✅ package built and inspected locally; `makepkg -si` (needs sudo) not run |

## Measured

- Reply latency with `gemma3:4b` on a GTX 1050 Ti: ~8–9 s per reply, flat over time
  (previously grew from 7 to 13 s). Synthesis 0.1–0.5 s. See `04-ollama.md`.
- Engine memory, 800 messages through the full pipeline (fast fakes, after filling all bounded
  structures): **+3 KB** for the last 400 messages (tracemalloc). A first run looked like a leak
  (+9 KB/message) but the growth came from the test doubles recording every call — confirmed
  by re-running with non-recording doubles.
- Overlay, 400 speeches + 57 character switches: geometries and textures back to baseline after
  fixing the skeleton-texture leak; JS heap flat (coarse metric).

## Known limitations

- Reply latency is bounded by the GPU: Gemma 3 does not reuse the prompt cache in this Ollama
  version; a Qwen-family 4B model should be faster (not measured).
- Speech starts after the whole reply is generated (no sentence streaming yet).
- Kokoro voices are not synthesized yet (listed by TTS BigLinux).
- No obs-websocket automation; the Browser Source is added by hand (with in-app steps).
- Interface language change needs a restart.
- Mouth movement is driven by loudness, not phonemes (TTS BigLinux exposes no timing data).
- The chat reader depends on YouTube's web endpoints; format changes are reported clearly but
  would need an update.
- Twitch/Rumble connectors are not implemented (the connector interface is ready).

## Recommended next steps

1. Measure `qwen3.5:4b` and, if faster, make it the default suggestion.
2. Stream sentence by sentence to TTS to start speaking ~3 s earlier.
3. obs-websocket: create/update the Browser Source after explicit consent.
4. Optional YouTube Data API connector (official, OAuth) as an alternative reader.
5. Live retranslation (`QQmlEngine.retranslate()`) for instant language switching.
6. More reactions/animations per character and keyword-triggered reactions.
