# 06 — Voice with TTS BigLinux (`core/tts.py`)

## What TTS BigLinux offers (tts-biglinux 4.1.0, inspected)

- `biglinux-tts --speak` reads the *selected text* and hands it to the running GTK app — not a
  synthesis API, so ChatToon does not use it.
- Python modules in `/usr/share/biglinux/tts-biglinux`: `services.voice_manager`
  (`discover_voices()`, `engine_availability()`), `services.text_processor.process_text()`
  (abbreviations, numbers, times, Markdown, URLs) and the parameter mappings in
  `services.tts_service` (`piper_length_scale`, `espeak_wpm`, …).
- Native module `/usr/lib/tts-biglinux/tts_engine.so`: `synthesize_piper()` and
  `synthesize_espeak()` return WAV bytes; `load_piper()` prewarms a model.
- Engines: RHVoice (`RHVoice-test`), espeak-ng, Piper, Kokoro. User choice is stored in
  `~/.config/biglinux-tts/settings.json`.

## How ChatToon uses it

ChatToon imports those modules (appended to `sys.path`, so they never shadow its own) and:

1. lists the voices of every *ready* engine; each character gets the voice you choose or the
   best match for its hints (e.g. Minhoca → Letícia/RHVoice), falling back to the voice
   selected in the TTS BigLinux app;
2. normalises the text with `process_text` (emoji removed first, URLs not read);
3. renders **one WAV**: Piper and espeak-ng through `tts_engine` (falling back to their
   commands), RHVoice through `RHVoice-test -o file`; text always goes through stdin, never a
   shell;
4. computes a loudness envelope (RMS, 50 per second, normalised at the 95th percentile) for
   lip sync;
5. plays it **once**, either with `pw-play`/`paplay`/`aplay` (desktop) or in the OBS source.

Kokoro is listed by TTS BigLinux but not synthesized by ChatToon yet (reported as unsupported).

## Measured (this machine)

| Voice | Audio | Synthesis |
|---|---|---|
| Letícia (RHVoice) | 3.1 s | 0.49 s |
| Faber (Piper, medium) | 1.9 s | 1.6 s cold, 0.07 s warm |
| espeak-ng pt-br | 2.4 s | 0.01 s |

Piper models are prewarmed on Start, so the first viewer does not wait 1.6 s.

## No double voice

The old prototype spoke with `spd-say` *and* the browser's `SpeechSynthesis`. Now: the overlay
never synthesizes; a reply is rendered once; the speech lock allows one utterance at a time;
in *Inside OBS* mode only the most recent OBS source receives the audio URL (others animate
silently); if no OBS source is connected the app plays it. Tested in
`test_engine.py::test_demo_flow_speaks_each_reply_exactly_once` and
`test_tts_overlay.py::test_overlay_audio_goes_to_one_sink_and_ws_is_read_only`.
