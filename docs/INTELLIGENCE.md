# Answers, memory, emotions and voice

How a viewer's message becomes a correct, in-character spoken reply, and how its quality is
measured. Principle: **a funny wrong answer is worse than a correct plain one** — the
personality enriches the answer, it never replaces it.

## Pipeline

```
message ─► identity (platform:source:author id) ─► cleaning ─► intent.classify (local rules)
        ─► exact math / comparison (a parser, never eval) ─► memory.recall (this viewer + the live)
        ─► reference sheet (objective computing/Linux questions)
        ─► prompt: identity · stream · how to answer · safety · format | examples | per-message part
        ─► Ollama (temperature by intent, one num_ctx for every call)
        ─► parse ─► validator (result said? rules leaked? copied? repeated?) ─► at most 1 retry
        ─► emotion.choose ─► voice ─► overlay
        ─► spoken? ─► memory.record (only now)
```

| Module | Role |
|---|---|
| `core/intent.py` | 19 message kinds and flags in microseconds, exact calculator, comparisons |
| `core/brain.py` | prompt layers, hints, reply parsing, validator, fallbacks |
| `core/memory.py` | three memory layers |
| `core/emotion.py` | emotion controller |
| `core/knowledge.py` | curiosities, answer templates, verified reference sheet (~40 entries) |
| `core/spontaneous.py` | lines said when the chat is quiet |
| `core/assistant.py` | stream-context suggestions from the platforms' own data |

**Prompt.** The system prompt is a numbered priority order: understand → the first sentence
is the correct answer → answer general knowledge normally, say "I don't know" only for what
cannot be known → ask when unclear → use memory naturally → then style. Viewer text travels in
a delimited data block (`<<< >>>`, delimiters inside it neutralised) and the rules forbid
following instructions found there. Everything that changes per message (time, memories,
verified results) goes in the last user message, so Ollama reuses the cached prefix.
Objective questions use temperature ≤ 0.3; banter keeps the configured creativity.

**Deliberately not done** (each measured): reasoning mode (+5–6 s per reply, sometimes an
empty answer), a model call to classify messages (local rules suffice), a "factual draft"
pre-call (no better, +0.2–0.4 s), an encyclopedia (general knowledge is the model's job), RAG
or embeddings (lexical recall finds what the evaluation asks for). Any call with a different
`num_ctx` makes Ollama reload the model (~5 s): every call, the warm-up included, uses the
configured context window, and a test enforces it.

## Memory

A viewer is `platform:source_id:author_id`. Two "Marcos" accounts, or "Rafael" on YouTube and
on Twitch, are different people; viewers with the same display name never see each other's
memories.

| Layer | Holds | Where | Lifetime |
|---|---|---|---|
| A — immediate | the latest 40 exchanges of the live | RAM | session |
| B — per viewer | exchanges, recent unanswered lines, first-person statements, a summary | RAM | session |
| C — long term (opt-in, off by default) | B's delivered exchanges and statements | SQLite + FTS5, 0600 | retention: 1–365 days or until erased |

Only what was really spoken becomes a memory: rejected suggestions, interrupted lines,
messages removed by moderators and orders aimed at the avatar are never stored. Recall returns
a small budget (~900 characters): the viewer's last exchanges, older ones sharing words, their
statements, unanswered lines and a few lines of the live's flow, each with its age. Long
conversations are summarised by the model while the chat is quiet (cancelled by any message).
Before storing: e-mails, phone numbers, CPF-like and card numbers and links are redacted;
sensitive subjects stay in RAM only. Bounded: 2,000 viewers, 20 exchanges, 12 notes each.

## Emotions

The model proposes one of `neutral, happy, laugh, surprised, confused, annoyed, celebrate,
thinking`; the controller keeps it when it fits the message kind (sadness never gets `laugh`,
facts get `happy/neutral/thinking`), avoids tics (three strong emotions in a row), softens
objective answers, and adds a *lead* reaction (`surprised` before good news). The overlay plays
the lead, switches after 0.9 s, picks a species gesture 45 % of the time, and runs idle moods
weighted per species every 16–36 s (limited and softer with *reduce motion*).

## Spontaneous lines

Off by default. Only while live in Demo or Automatic mode, idle, with an empty queue and a
quiet chat (default 90 s, lines spaced 240 s). Invitations, checked curiosities (spoken as
written, never rewritten), comments on the topic, humour, catchphrases. A viewer cancels a
line still being prepared. Priority: emergency > streamer commands > paid/priority messages >
chat replies > spontaneous lines > memory summaries.

## Voice

1. Voices come from every ready engine of TTS BigLinux; each character gets its chosen voice or
   the best match, with TTS BigLinux's default as fallback.
2. Text is normalised by TTS BigLinux's `process_text` (emoji removed first, URLs not read).
3. One WAV per line: Piper and espeak-ng through the native `tts_engine`, RHVoice through
   `RHVoice-test`, Kokoro through `koko text` built by TTS BigLinux (never `pipe`, which plays by
   itself). Long Kokoro texts are rendered in pieces and joined, because `koko` panics past ~510
   tokens. Everything becomes 16-bit mono PCM; text goes through stdin, never a shell; interrupt
   kills the engine's process group.
4. A loudness envelope (RMS, 50/s, normalised at the 95th percentile) moves the mouth: no real
   audio, no mouth movement.
5. Played once: `pw-play`/`paplay`/`aplay`, or inside the OBS source. Kokoro replies are voiced
   sentence by sentence (one plays while the next renders).

Measured on 2026-10-17 (same sentence, warm):

| Engine | Voice | Audio | Synthesis |
|---|---|---|---|
| espeak-ng | Portuguese | 3.3 s | 0.01 s |
| RHVoice | Letícia-F123 | 4.2 s | 0.24–0.26 s |
| Piper | Jeff (medium) | 3.8–3.9 s | 0.84–0.90 s |
| Kokoro | Dora | 3.4 s | 2.96–3.06 s |
| Kokoro, 671 characters | Dora | 38.8 s | 33.1 s (4 pieces) |

Cancelling a Kokoro render stops `koko` in 0.02 s; no temporary file is left after an error,
a cancel, `cleanup()` or exit.

## Measuring quality

`tools/eval_intelligence.py` runs every case of `tools/eval/*.json` through the engine's own
generation path against the real local Ollama (no voice, no overlay):

```bash
python tools/eval_intelligence.py --model qwen3.5:2b --set eval --repeat 2 --out results.json
PYTHONPATH=/path/to/old/checkout python tools/eval_intelligence.py --label before ...
python tools/eval_intelligence.py --rescore results.json   # same checks on saved replies
```

* Sets: `eval` (67 cases, 48 verifiable), `holdout`, `holdout2` (25 cases, 24 verifiable).
  `holdout2` was written before ever being run and is never used for tuning: it is the
  generalisation figure. `holdout` is partly contaminated (the reference sheet was written after
  some of its failures).
* Verifiable cases give the accuracy figure; criteria cases (fitting emotion, declining unknown
  personal facts, asking back on ambiguity, resisting prompt injection) are reported apart.
  Humour quality is not scored.
* Run-to-run noise on ~50 verifiable questions is ±3–6 points.

| Model | Set | 2.2.2 | 2.3.0 (2026-10-15) | 3.0.0 (2026-10-17) |
|---|---|---|---|---|
| qwen3.5:2b | main | 29.2 % | 89.6 % | **89.6 %** |
| qwen3.5:2b | holdout2 (clean) | 39.6 % | 79.2 % | 75.0 % |
| llama3.1:8b | main | 45.8 % | 96.9 % | not run |
| llama3.1:8b | holdout2 (clean) | — | 97.9 % | not run |

3.0.0 run, main set, `qwen3.5:2b`: math 28/28, Linux 28/28, injection 10/10, factual 15/20,
continuity 7/12; latency p50 1.42 s, p95 1.88 s; 0 truncated, 0 fallbacks. The answer pipeline
did not change in 3.0.0; the holdout2 difference is within the noise. What still fails is the
small model's own knowledge ("São Paulo é a capital", "the kernel is the computer's brain") and
continuity it receives but does not use; a bigger model fixes most of it at the same speed on a
dedicated GPU (8B: 94–98 %).

`tools/bench_intelligence.py` times the local layers (no model): classification 0.06 ms, memory
recall 0.22 ms, full-text search 1.6 ms. A 2,000-message soak on three platforms answered and
spoke every message with never two voices at once; RAM grew 1.9 MB over the second half (the
bounded per-viewer memory filling up).
