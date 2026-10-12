# 12 — Characters, Kokoro and message reading (ChatToon 2.1)

This document records the work behind ChatToon 2.1: the diagnosis, the technical
decisions and how each part was built and verified. It is a record only — nothing in it is
needed to run the application.

## 1. Diagnosis (starting point: 2.0.0)

### Speech paths

| Where | Path before 2.1 |
|---|---|
| Synthesis | `core/tts.py` `BigLinuxTTS.synthesize()` → Piper/espeak-ng through the native `tts_engine`, RHVoice through `RHVoice-test`; **no Kokoro branch** → `TTSError("Voice engine 'kokoro' is not supported…")` |
| Envelope | `analyse_wav()` with Python's `wave` module (16-bit PCM only) |
| Playback | `AudioPlayer` (`pw-play`/`paplay`/`aplay`) **or** the OBS browser source (`OverlayServer.speak`, one audio sink) |
| Order | `ChatToonEngine._answer()` → `generate()` → `speak()` under `_speech_lock` |
| Overlay | WebSocket events `config`, `state`, `speak`, `done`, `stop`, `react` |

### Why Kokoro voices were silent

1. `BigLinuxTTS.synthesize()` had no `kokoro` branch: choosing a Kokoro voice always ended
   in "not supported", although TTS BigLinux listed the voices (its catalog was used).
2. Even with a branch, `koko text` writes **stereo 32-bit float WAVE_FORMAT_EXTENSIBLE**
   (inspected: `fmt` tag `0xFFFE`, sub-format 3, 24 kHz). Python's `wave` raises
   `unknown extended format`, so the lip-sync analysis would have crashed.
3. The TTS BigLinux app speaks Kokoro with `koko pipe`, which **plays every sentence
   itself** while writing the WAV. Reusing that path would make ChatToon heard twice.

Installed versions inspected: `tts-biglinux 1:4.1.0-3`, `biglinux-kokoro-tts 26.10.09`
(`/usr/sbin/koko`, model `/usr/share/biglinux-kokoro-tts/model/model.onnx`, voices in
`~/.local/share/biglinux-tts/kokoro-voices/voices.bin` or the system copy). Installed
voices: af_heart, ef_dora, ff_siwis, hf_alpha, if_sara, jf_alpha, **pf_dora**, **pm_alex**,
**pm_santa**, zf_xiaobei.

`koko text` was checked with every audio server made unreachable (`PULSE_SERVER`,
`ALSA_CONFIG_PATH`, `XDG_RUNTIME_DIR` pointing nowhere): it still renders the file, so it
never plays audio. Cost on this machine (16 threads): ~1 s to load the model, then roughly
real time (≈ 0.05 s per character); long texts (791 characters) are split by `koko text`
itself without the 510-token panic `koko pipe` has.

### Characters and animation

Minhoca, E.T. and Tux were procedural Three.js models sharing `rig.js` (eyes, lids, brows,
morph mouth, emotion presets, blink, gaze, one-shot reactions). Between replies they only
blinked, moved their eyes and swayed; there was no state machine beyond the phase
(idle/thinking/speaking), no random gestures and no settings for motion.

## 2. Decisions

| Topic | Decision | Why |
|---|---|---|
| Kokoro command | `services.kokoro_voice_service.build_koko_command(..., text=…, output=…)` → `koko text` | Same model, voices.bin, language and speed mapping as TTS BigLinux; renders a file without playing |
| Kokoro checks | `koko_problem()` before every render | Missing binary/model/voices.bin/voice give TTS BigLinux's own translated message |
| Text | `process_text()` (abbreviations, numbers…) then `prepare_koko_text()` | koko fails on punctuation-only pieces (`?!`, `...`) |
| Audio format | `to_pcm16()`: any RIFF WAV (8/16/24/32-bit PCM, 32/64-bit float, extensible, streaming headers) → mono 16-bit PCM | One format for the envelope, `pw-play` and the OBS source |
| Volume | gain from the TTS BigLinux scale (50 = ×1, 100 = ×2), limited to the peak | koko has no volume option; no clipping |
| Pitch | not offered for Kokoro (slider disabled with an explanation) | koko has no pitch control: no dead controls |
| Speed | `kokoro_speed(rate)` (0.5–2.0) | TTS BigLinux's own mapping |
| Processes | `Popen` in a new session, `communicate(timeout)`, `cancel()` kills the process group and reaps it | Interrupt/emergency stop a 40 s render at once; no zombies |
| Cancel scope | an epoch counter: `cancel()` drops the running render **and** renders queued behind the engine lock | No CPU burnt after an emergency stop |
| Latency | Kokoro lines are voiced **sentence by sentence** (next sentence renders while the current one plays) | Time to first sound ≈ one short sentence instead of the whole reply |
| Reading | the viewer's own text, normalised for speech, never sent through the AI | The quote is exact; the AI cannot alter it; prompt injection is unaffected |
| Reading order | reading → pause → reply under the speech lock; the reply is generated **and voiced** while the reading plays | Never two voices; little extra waiting |
| Default | new installations: *Name + message*; settings saved by 2.0 keep answering directly (`reading` missing → `off`) | Requested default without changing existing streams |
| Animation | a `Director` per character (state machine + behaviour), characters map its values to their anatomy | One reusable system, six different bodies |
| New models | procedural (Three.js), references used only for proportions/colours | No image as a character, no third-party assets, nothing downloaded |
| Thumbnails | rendered from the real 3D models (`tools/render_thumbnails.py`) | Six cards without six WebGL contexts in the app |

## 3. Implementation

### 3.1 Kokoro (`core/tts.py`)

- `BigLinuxTTS._kokoro_render()` → `koko_problem()` → `prepare_koko_text()` →
  `build_koko_command(text=…, output=…)`; refuses any command that is not `koko text`
  (a future TTS BigLinux that returned a `pipe` command would play audio by itself).
- `_exec()` runs every engine process (koko, RHVoice-test, piper/espeak-ng fallbacks) with
  argv lists only (no shell), its own process group and a timeout
  (`KOKORO_TIMEOUT_BASE + chars × KOKORO_TIMEOUT_PER_CHAR`, max 300 s).
- `to_pcm16()` validates and converts (numpy when available, pure Python otherwise),
  rejects broken files (`invalid-wav`), and writes atomically.
- `prewarm()` renders "." once with Kokoro so the 90 MB model is in the page cache before
  the first viewer.
- Errors carry a `code` (`kokoro-unavailable`, `kokoro-timeout`, `kokoro-failed`,
  `no-audio`, `invalid-wav`, …) that the interface translates.
- `Voice.to_dict()` reports `pitch: false` for Kokoro; the voice page disables the slider.

### 3.2 Message reading (`core/reading.py`, `core/engine.py`)

- Modes: `off`, `name` ("Pergunta de Maria."), `name_message` ("Maria perguntou: …").
  Super Chats: "Bia mandou um Super Chat de R$ 10,00 e disse: …". English templates follow
  the reply language.
- `speakable_name()`: `@joao_linux1987` → "joao linux", `JoaoLinux` → "Joao Linux",
  YouTube's generated `@user-ab12cd34ef` or emoji-only names → "um espectador", fancy Unicode
  letters folded, random tokens and long digit runs dropped.
- `speakable_text()`: links → "link", emoji and `:shortcodes:` removed, `@`/`#` dropped,
  "kkkkkkk" → "kkk", "!!!" → "!", control/bidi characters removed (already by `clean_text`).
- `cut()`: at a sentence end when it keeps ≥ 45 % of the limit, otherwise at a word,
  with "…" — never rewritten. The bubble shows the same cut text (links shown as 🔗).
- Moderation: messages dropped by the selector (blocked words, commands, spam) never
  reach the reader; if the message touches a forbidden topic only the name is read.
- Engine: `_converse()` = listening → reading (segments) → pause (a paused stream holds the
  reply) → thinking (only if the reply is not ready) → speaking. Generation starts with the
  reading; the reply's first segment renders as soon as the reading's own segments are
  rendered (`rendered` event), so reading segments always come first. If the AI already
  failed, the message is not read at all.
- Assisted mode: nothing is read until the streamer approves; the suggestion card shows
  the line that will be read.
- Interrupt / emergency / character switch cancel the whole sequence (the TTS process too).
- Settings (`ReadingSettings`): mode, max characters (40–400), pause (0–3 s), reading voice
  ("" = the character's). Page **Voz → Leitura das mensagens**, with a live sample line and
  a preview button.

### 3.3 Overlay (`web/overlay/overlay.js`, `overlay.css`)

- `speak` events carry `kind` (`reading` | `reply`), a `group` id and, for segmented lines,
  `continue` + `progress` (share of the line), so the bubble keeps one text while segments
  play and reveals it smoothly.
- Reading bubble: a chat card (author pill with 💬, "no chat"/"pergunta"/"Super Chat" label,
  quoted italic text). After the reading it stays with three dots while the reply is
  prepared, then cross-fades into the reply — no blink, no stacking.
- Without real audio the mouth stays closed (only the standalone demo page simulates a
  syllable rhythm, and the app labels it "Animation demo · simulated lip sync").
- The bubble follows `bubbleAnchor` (an object on each character's head, above hats, ears
  and tufts), with hysteresis between "above the head" and "beside the head".
- `hear(text)`: when a message is picked the character can react to its words (the owl and
  Tux perk up at Linux/tech words, Tux is mock-offended by "Windows").

### 3.4 Animation system (`web/overlay/rig.js`)

`Director` produces, every frame and frame-rate independently (exponential damping, dt in
seconds, sub-stepped springs):

- **state** among idle, listening, reading, thinking, speaking, reacting, celebrating,
  paused, emergency, resolved from the engine phase + app state; blended **weights**
  (`w[state]`, ~0.5 s transitions) so poses cross-fade;
- **look**: eyes lead with saccades, the head follows at ~60 % with lag; listening looks at
  the audience, reading sweeps the eyes along the bubble line, thinking looks up-left,
  speaking holds eye contact with occasional glances away, paused looks down; big gaze
  shifts trigger a blink now and then;
- **posture** shifts (lean), **breathing** (slower when paused, faster when talking or
  excited), **speech beats** (impulse on envelope onsets → nods and hand/wing beats),
  **micro-expressions** (small smiles, brow raises);
- **gestures**: weighted random choice among the species gestures allowed in the current
  state, with cooldowns, never the same twice in a row, intervals scaled by *frequency*;
  generic ones (glance, look around, weight shift, curious tilt) for everybody;
- **settings**: idle on/off, intensity (subtle ×0.55, normal, lively ×1.45), frequency
  (low ×1.8 intervals, high ×0.55), reduce motion (amplitude ×0.45, slower, no gestures
  marked `big`, gentle reactions without jumps or spins).

`Character` keeps the expression/lip-sync/blink logic, adds slow blinks, `BeadEye` (toy-like
glossy eyes with lids that only appear to blink/squint and "^ ^" arcs for laughs), `Spring`,
`gesture(name)`, `hear(text)` and texture disposal.

### 3.5 Characters

| | Construction | Gestures |
|---|---|---|
| Minhoca | skinned ringed body (7 bones), dirt mound | stretch, wiggle, peek (retracts into the dirt), headBob, dig, sassy (talk) |
| E.T. | egg head, suit, spring antennae, hover ring | scan, beep (antennae + glow), wave, orbit, probe, point (talk) |
| Tux | one skinned lathe body (hips/chest/head bones) with a seamless painted face+belly, bead eyes, two-part beak, two-joint flippers, webbed feet, **top hat** on a spring | tipHat, adjustHat, flap, waddle, bow, stretch, bellyPat, explain/hatTouch (talk) |
| Gata | see §4 | tailWag, earTwitch, slowBlink, headTilt, curiousLook, silentMeow, pawRaise, faceWash |
| Coruja | see §4 | headTurn, wingOpen, wingFlap, sway, ruffle, hoot, surprisePuff, techExcited |
| Cachorro | see §4 | tailWag, earFlop, headTilt, pant, tongueOut, hop, pawRaise, joy, curiousSniff |

Shared procedural helpers live in `characters/shapes.js` (`latheBody` with smooth seam,
`markingTexture` + `markedMaterial` for seamless painted patches from signed-distance
shapes, `skinByHeight`, `boneChain`, `topHat`).

### 3.6 Personalities (`core/characters.py`)

Gata (sarcastic, clever, independent), Coruja (wise, observant, good-humoured) and Cachorro
(cheerful, playful, enthusiastic) have their own persona, examples, safe deflections,
default voice hints (Gata → Kokoro Dora, Coruja → Kokoro Alex, Cachorro → Piper Cadu),
personality dials, colour and default catchphrases. E.T. became "curious, tech-savvy and
unpredictable", Tux "geeky, elegant (top hat) and a free software champion". A new prompt
rule asks for tech/Linux jokes only when they fit the message or the stream topic. Every
character keeps its own persistent settings (voice, colour, personality, catchphrases).

### 3.7 Interface

- **Personagens**: six cards (thumbnail from the 3D model, species, tagline, voice),
  one-click selection, enlarged animated view per character with expression/gesture
  buttons; a live "Try" panel on the real overlay (expressions, gestures, voice test,
  simulated viewer message → reading + AI reply, simulated reply); **Animações em repouso**
  (on/off, intensity, frequency, reduce motion).
- **Voz**: engine status chips (RHVoice, espeak-ng, Piper, Kokoro), engine names in the
  voice list, pitch disabled for Kokoro, **Leitura das mensagens**.
- **Painel**: phases "Aguardando mensagens / Prestando atenção / Lendo a mensagem /
  Pensando / Falando"; assisted suggestions show the line that will be read.
- Errors from the engine carry codes and are shown in the interface language.

## 4. Results (2026-10-11, this machine: 16 threads, PipeWire, Ollama 0.33.3)

### New characters

| | Construction | Draw calls / triangles (high · low) |
|---|---|---|
| **Tux** | skinned lathe body, painted face+belly, bead eyes, two-part beak, flippers, feet, top hat | 26 · 29 k / 26 · 9.8 k |
| **Gata** | big-cheeked head with painted stripes, muzzle and chest; huge amber eyes with lash lines and slit/dilating pupils; spring ears with pink insides; "ω" mouth rebuilt on the curved face; bending front legs with toe bumps and pink pads; 10-bone striped tail | 34 · 54 k / 34 · 14 k |
| **Coruja** | one skinned body with the head built in (far head turns without seams); cream/amber streaked eyes with dilating pupils in raised rims; hooked two-mandible beak; spring ear tufts; instanced chest spots; wings with shoulder, elbow and a 4-feather fan; static bark branch with toes and claws gripping it | 41 · 52 k / 34 · 13 k |
| **Cachorro** | seamless head (skull, cheeks, muzzle) with painted blaze and eye patches; big glossy eyes with lash lines and curved brows; glossy nose; own mouth with chin drop, maroon inside and 3D tongue; 3-bone spring ears; sitting body with bending front legs; 5-bone spring tail | 41 · 75 k / 39 · 17 k |

(Counts include the contact shadow; measured in headless Chrome.) Each new model was compared
side by side with its reference over 15+ rounds of screenshots: front, 3/4, side, close-ups,
every expression, every gesture mid-pose, talking, low quality, colour override and reduced
motion; 30–60 s randomised soaks found no NaN.

### Kokoro

- Real synthesis through ChatToon: `pf_dora` 2.95 s of audio in 2.9 s; `pm_alex` 8.95 s in
  8.3 s (alone on the CPU). Speed works (same sentence: 1.43 s fast, 3.80 s slow). Cancel
  returns in 0.03 s with no `koko` left running. Missing voice → TTS BigLinux's own
  translated message. Piper, RHVoice and espeak-ng unchanged.
- Full real flow (Ollama `llama3.1:8b` + Kokoro `pm_alex` + `pw-play`): listening → reading
  "Carlos perguntou: …" → reply, each played once, never overlapping (the player reported no
  audio playing when the next one started); the reply was generated and voiced during the
  reading. The run happened while three headless browsers were rendering on the CPU, so
  Kokoro took ~2× its normal time there.
- "Inside OBS" path with real Kokoro audio: a Chromium page in the OBS role (the engine OBS
  embeds) decoded every segment (2.08 / 2.93 / 2.00 / 2.93 s) and played each to the end
  before the engine sent the next; the desktop player was never used.

### Switching characters

Construction is ~25–380 ms (Tux paints its face texture once; it is cached afterwards).
First-frame shader compilation in software WebGL took 1.5–3.7 s — now done in the background
with `compileAsync` while the previous character keeps animating.

### Tests

`python -m pytest`: **164 passed**, 5 skipped (live tests) — including the six browser tests
over all six characters (~3.5 min with software WebGL). `--run-live`: real Kokoro (`pf_dora`,
`pm_alex`), real TTS BigLinux and real Ollama pass (`CHATTOON_LIVE_MODEL=llama3.1:8b`; the
first installed model here, `smallthinker`, returns empty answers to the full character
prompt — a model limitation, also present in 2.0).

### Not verified automatically / pending

- OBS Studio itself was not driven (it is installed, but automating it would change the
  user's scene collection); its browser engine was tested through Chromium.
- Audio was heard through `pw-play` on this machine at low volume; no recording/listening
  test of the OBS stream mix.
- Celebrations for new members/subscribers: the public live chat does not deliver those
  events reliably, so they were not implemented.
- Known model limitations: Gata's eyes protrude slightly (closed lids show as domes, the far
  eye bulges a little at 3/4); Gata's inner ears keep their pink when the colour is changed;
  Cachorro's mouth is laid onto the muzzle (from the side it reads as a surface) and its ear
  roots show a small fold; Coruja's head turn is capped at ~86°.
