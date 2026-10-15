# 28 — Validation results

Everything here was measured on 2026-10-15 with the real local Ollama 0.33.3 (Radeon RX
9060 XT). The raw replies of every run are reproducible with `tools/eval_intelligence.py`.

## Method

* **Sets** (`tools/eval/`): `eval` (main, 67 cases, 48 verifiable) — math, logic, facts,
  Linux, continuity, unknown personal facts, ambiguous messages, humour, greetings, good
  news, feelings, prompt injection; `holdout` (26 verifiable); `holdout2` (25 cases, 24
  verifiable).
* **Honesty rules**: `holdout2` was written *before* it was ever run and was never used
  to tune anything; it is the generalization figure. `holdout` became partly contaminated
  (the reference sheet was written after seeing some of its failures) and is reported
  separately. A checker bug (a quoted `'cd'` was not accepted) was fixed during the
  work; every saved run, before and after, was re-scored with the same checker
  (`--rescore`).
* **Verifiable cases** count for the accuracy goal: number said (digits or words), name
  or term present, and for the negative continuity cases, the *other* person's fact
  absent. **Criteria cases** are reported separately and never mixed into accuracy:
  the emotion must fit (greeting, good news, joke, sadness), unknown personal facts must
  be declined, ambiguous messages must get a question back, prompt injections must not be
  obeyed or leak the rules. No percentages are claimed for humour quality, which is
  subjective.
* **Conditions**: each case runs in a fresh engine with the streamer's real settings
  (Tux, creativity 0.9), through `engine.generate()` (the live's own path: classifier,
  memory, prompt, validation, emotion). Continuity cases first run their setup
  conversation and commit each reply as spoken. Each set runs twice (sampling varies).
* **Known checker artifact**: runs happened between 1 and 4 a.m.; the avatar uses the real
  time, so "Bom dia, Tux!" sometimes gets "Boa madrugada", which the greeting check counts
  as a miss.

## Before and after (shipped code)

| Model | Set | 2.2.2 | New | Latency p50 (2.2.2 → new) |
|---|---|---|---|---|
| qwen3.5:2b | main | 29.2 % | **89.6 %** | 1.27 → 1.46 s |
| qwen3.5:2b | holdout | 34.6 % | **84.6 %** | 1.17 → 1.42 s |
| qwen3.5:2b | holdout2 (clean) | 39.6 % | **79.2 %** | 1.08 → 1.33 s |
| llama3.1:8b | main | 45.8 %¹ | **96.9 %** | 1.27 → 1.21 s |
| llama3.1:8b | holdout | — | **94.2 %** | → 1.16 s |
| llama3.1:8b | holdout2 (clean) | — | **97.9 %** | → 1.22 s |

¹ one run. These are the runs of the exact final code. The previous run (before the last
prompt and validator polish) gave 87.5 / 88.5 / 83.3 % (2B) and 99.0 / 98.1 / 89.6 % (8B):
run-to-run variation on ~50 verifiable questions is ±3–6 points, so differences of that size
between runs mean nothing.

Criteria cases (main set): 55.3 % → 92.1 % (2B), 84.2 % → 97.4 % (8B).

**Against the 95 % goal**: reached with `llama3.1:8b` on the main and clean held-out sets
(94.2 % on the contaminated holdout); across the last two runs the 8B model stayed between
89.6 % and 99.0 %. Not reached with `qwen3.5:2b`: the remaining errors are
the model's own general knowledge (see below), which no prompt can supply. The streamer's
GPU runs the 8B model at the same speed.

### Per category, main set (2 runs)

| Category | 2.2.2 (2B) | New (2B) | 2.2.2 (8B, 1 run) | New (8B) |
|---|---|---|---|---|
| math | 7/28 | **28/28** | 6/14 | **28/28** |
| logic | 1/8 | **8/8** | 3/4 | **8/8** |
| factual | 8/20 | 17/20 | 3/10 | **20/20** |
| Linux | 9/28 | 25/28 | 10/14 | **28/28** |
| continuity | 3/12 | 8/12 | 0/6 | 9/12 |
| unknown personal facts | 1/6 | 5/6 | 1/3 | **6/6** |
| ambiguous | 0/4 | 3/4 | 2/2 | **4/4** |
| feelings (sad, tired) | 0/4 | **4/4** | 1/2 | **4/4** |
| good news | 1/4 | **4/4** | 2/2 | **4/4** |
| injection | 10/10 | **10/10** | 5/5 | **10/10** |

### Emotions (main set, 2B)

| | laugh | happy | thinking | annoyed | celebrate | neutral | confused | surprised |
|---|---|---|---|---|---|---|---|---|
| 2.2.2 | **123** | 1 | 4 | 4 | 0 | 0 | 1 | 1 |
| new | 14 | 86 | 20 | 4 | 4 | 4 | 2 | 0⁴ |

⁴ Surprise is now played as a *lead* before the line's own emotion (good news, problems),
so it does not appear as a final emotion here.

### How each step contributed (qwen3.5:2b, main / holdout2)

| Step | Main | Holdout2 |
|---|---|---|
| 2.2.2 | 29.2 % | 39.6 % |
| v1: priority prompt, classifier, exact math, memory, emotion controller | 75.0 %⁵ | — |
| v2: viewer facts next to the question, "about you" questions, reference sheet, homonym fix | 85.4 % | 72.9 % |
| v3: acronym hint, second homonym fix, objective temperature 0.3 | 92.7 % | 79.2 % |
| v4: balanced "say you don't know" rule (fixed the 8B model refusing easy facts) | 87.5 % | 81.2 % |
| final: validator false positive, references only for real questions, stronger recall hints | 89.6 % | 83.3 % |
| "aquele problema" is not a follow-up; questions about the live itself | 87.5 % | 83.3 % |
| shipped: time mentioned only when relevant, repeated lines caught, call-to-action punctuation | 89.6 % | 79.2 % |

⁵ one run. The 2B numbers between v3 and the shipped code are within run-to-run noise. v4's
rule change matters mostly for the 8B model: 83.3 % → 97.9 %.

### Ablations

* Without the verified reference sheet (v3): main 92.7 % → 79.2 %, Linux 28/28 → 9/14.
* Objective temperature 0.0 instead of 0.3: no better (main 90.6 %, holdout2 75.0 %).
* "Factual draft" pre-call: no better, slower; removed (see 27).

## What still fails

* **General knowledge of the 2B model**: "São Paulo é a capital do Brasil" (sometimes),
  "Giotto pintou a Capela Sistina", "o leão é o maior animal", "BigLinux deriva do Arch"
  even with the reference saying Manjaro. The bare model makes some of the same mistakes.
* **8B knowledge slips**: "PDF = Porta Documentos Eletrônicos", "HTML estiliza páginas"
  (that is CSS), "Argentina é o maior país da América do Sul".
* **Continuity that the model does not use**: the memory delivers the right facts to the
  right person (unit tests and prompt dumps), but the 2B model sometimes answers around
  them ("Lembro! Seu app…" without saying Python/QML).
* **Guessing instead of declining** on negative same-name cases: the prompt for the
  second "Rafael" contains nothing about the first, yet the model may list languages
  ("C ou Python") or colours ("azul ou verde"). Counted as failures.

## Scenario matrix (task 13.1)

| Scenario | Result | Where |
|---|---|---|
| "2+2" | 4, always (computed) | eval math 28/28; `test_intent`, `test_the_verified_result_is_always_said` |
| Linux technical question | correct with the reference sheet | eval Linux; `test_reference_sheet_*` |
| Ambiguous question | asks back | eval ambiguous 3/4 (2B), 4/4 (8B) |
| Unknown factual (personal) question | declines | eval unknown 5/6 (2B), 6/6 (8B) |
| Humour | fitting emotion, playful | eval humour 6/6 (2B) |
| Conversation resumed after several messages | recalls the right facts | `test_follow_up_after_other_viewers`; eval continuity |
| Two users with the same name | never mixed | `test_same_name_*` (memory and engine); eval cont-04/06, h2-cont-03 |
| Same user on two sources | separate identities | `test_same_name_on_two_platforms_*` |
| App restart | saved memories come back | `test_persistence_survives_a_restart_and_respects_settings` |
| Memory disabled / saving off | nothing written | `test_persistence_off_writes_nothing`, `test_memory_disabled_recalls_nothing` |
| Message removed by a moderator | leaves queue, reply and memory | `test_moderation_and_streamer_erasure`, `test_moderators_removals_reach_the_memory`, existing retraction tests |
| Good news | surprised → celebrate | `test_good_news_gets_a_lead_reaction…`; overlay test; screenshots |
| Joke | laugh | eval humour; `test_emotion_fits_the_message` |
| Hard question | thinking pose while generating (existing), `thinking` allowed for explanations | eval emotions |
| Celebration | celebrate + species gesture | overlay tests, screenshots |
| Long silence | spontaneous line when enabled | `test_spontaneous_line_when_the_chat_is_quiet` |
| Busy chat | spontaneous lines never interrupt replies | `test_a_viewer_cancels_a_spontaneous_line_being_prepared`, gating test |
| Emergency stop | everything stops, nothing spoken after | existing emergency tests + spontaneous gating test |
| Two platforms at once | unchanged multistream behaviour | existing `test_streams_core`, `test_gui_multistream` |
| Description suggestion | editable proposal, applied only on approval | `test_ai_fields_*`; dialog screenshots |
| Metadata API failure | clear code, nothing lost | `test_metadata_failures_become_clear_codes` |
| Source without data | nothing invented | `test_guests_and_empty_sources_are_never_invented` |
| Kokoro TTS | real voices synthesize | live tests `test_real_kokoro_voice[pf_dora, pm_alex]` |
| OBS Studio | **not run** | the overlay page is the same one OBS loads; verified in headless Chromium only |
| Reduce motion | idle moods limited and softer | `test_idle_moods_follow_the_species_and_respect_reduce_motion` |
| Prompt injection | not obeyed, nothing remembered | eval injection; `test_orders_*`, `test_a_prompt_leak_is_never_spoken` |
| Ollama unavailable | error shown, no crash, live keeps running | `test_model_unavailable_never_crashes`, spontaneous fallback test |

## Automated tests

`python -m pytest -q`: **450 passed, 6 skipped** (before this work: 314 passed). The six
skipped tests need `--run-live`. With `--run-live`: real Ollama reply, real TTS BigLinux,
two real Kokoro voices pass; the YouTube live test is skipped (no live stream URL).

New test files: `test_intent.py` (classifier, calculator, safety), `test_memory.py`,
`test_intelligence.py` (prompt, validator, emotions, spontaneous scheduler, reference
sheet), `test_engine_intelligence.py` (whole pipeline with a scripted model: retries,
memory only after speaking, interrupted lines, moderation, homonyms, spontaneous
priorities, summaries, diagnostics, one `num_ctx` for every call), `test_assistant.py`,
`test_overlay_emotions.py` (real page in headless Chromium).

Also run: `python -m chattoon doctor` (Ollama, 178 voices incl. 10 Kokoro, memory and
spontaneous status), `python -m chattoon ask "Quanto é 2+2?" --character tux`, ruff (clean
on all changed files), a 2,000-message soak (see 27), and the section 17 conversation end
to end with the real model and a real voice.

## Visual validation

Seen by eye (offscreen rendering of the real QML app with realistic data, software
renderer, both themes where noted):

* AI page — answer quality, conversation memory, generation diagnostics (dark, light);
* Live chat — memory panel with one viewer's conversation and notes, "lembrou" chips, list
  (dark, light);
* Stream context — "From your sources" and the AI assistant dialog (dark, light);
* Settings — spontaneous lines, memories, privacy (dark);
* Characters — curiosities and spontaneous lines (dark, light);
* Overlay (headless Chromium, WebGL) — Tux, Cachorro and Gata during a surprised lead and
  after switching to celebrate.

Fixed after looking: the retention combo showed "1 dia" for 30 days; "1 memórias"
(plural); a "reference" chip on greetings; "(official)" untranslated; History labelled
exact results and spontaneous lines as "safe reply".

**Not verified visually**: the app on a real display (the user's session was not taken
over), the 3D preview inside the app (QtWebEngine does not render offscreen), and OBS
Studio itself.
