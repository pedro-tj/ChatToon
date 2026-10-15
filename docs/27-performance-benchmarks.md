# 27 — Performance

Goal: better answers without making the live slower. Machine used for every number here:
Ryzen (16 threads), 46 GB RAM, Radeon RX 9060 XT (16 GB), Ollama 0.33.3, BigLinux,
models `qwen3.5:2b` (the streamer's) and `llama3.1:8b`.

## Reply latency (model generation, end to end per message)

Measured by `tools/eval_intelligence.py` over every case of the main set (2 runs each):
the time `engine.generate()` takes, prompt building, memory, validation and any retry
included. Voice synthesis is separate (below).

| Configuration | Main set p50 | p95 | Avg prompt tokens | Model calls / case |
|---|---|---|---|---|
| 2.2.2, `qwen3.5:2b` | 1.27 s | 1.69 s | 925 | 1.00 |
| new, `qwen3.5:2b` | 1.46 s | 1.90 s | 1,313 | 1.02 |
| 2.2.2, `llama3.1:8b` | 1.27 s | 1.89 s | 1,008 | 1.00 |
| new, `llama3.1:8b` | 1.21 s | 2.47 s | 1,441 | 1.01 |

On the held-out sets the new pipeline's p50 is 1.16–1.42 s for both models. Retries (a
reply that misses a verified result, leaks its rules or repeats a recent line) are rare:
1–3 in 134 replies on the main set. No reply
was truncated by the token limit in any run. On this GPU the 8B model is as fast as the
2B one; on a CPU-only computer the difference would be large (not measured here).

The prompt grew from ≈ 925 to ≈ 1,300 tokens (memory, hints, reference). It costs little
because the system prompt is identical between messages: Ollama reuses the cached prefix,
and only the per-message tail is evaluated.

## What was tried and rejected (measured)

| Idea | Accuracy | Latency | Decision |
|---|---|---|---|
| Reasoning mode ("think") for objective questions | fixes some facts | **+5–6 s**, sometimes spends all tokens thinking (empty answer) | off |
| Temperature 0.0 for objective questions (vs 0.3) | 90.6 % vs 92.7 % main, 75.0 % vs 79.2 % held-out | same | 0.3 |
| "Factual draft" (persona-free pre-call) | 89.6 % = 89.6 % main; 75.0 % vs **83.3 %** held-out (2B); 93.8 % vs **95.8 %** (8B) | +0.2–0.4 s | removed |

### A trap found on the way: model reloads

The first draft version used a smaller `num_ctx` (2048) than the chat calls (4096).
Ollama reloads a model whenever `num_ctx` changes: every draft cost ≈ 5 s and the p95
reached 11 s. Every call (replies, retries, spontaneous lines, summaries, the context
assistant) now uses the configured context window, and so does the warm-up `preload`,
which before loaded the model with Ollama's default size, so a different default would
reload it on the first viewer. A regression test checks that all calls share one
`num_ctx`.

## Local layers (no model): `tools/bench_intelligence.py`

| Operation | p50 | p95 |
|---|---|---|
| classify a message (+ exact math) | 0.059 ms | 0.078 ms |
| reference-sheet lookup | 0.025 ms | — |
| record an exchange (SQLite, 6,000 saved, 1,500 viewers) | 0.149 ms | 0.217 ms |
| recall (RAM + database) | 0.222 ms | 0.355 ms |
| recall after a restart (database only) | 0.217 ms | 0.364 ms |
| full-text search (FTS5) | 1.57 ms | 1.98 ms |
| list of remembered viewers | 2.25 ms | — |

Database: ≈ 1.2 KB per saved exchange (7.3 MB for 6,000). RAM for 1,500 viewers and 6,000
exchanges: 10 MB. RAM is bounded: at most 2,000 viewers (least recently seen leave first),
20 exchanges, 12 notes and 6 unanswered messages each; older exchanges stay on disk when
saving is on.

## Long live (soak)

2,000 messages from 300 viewers on three platforms through the whole engine (selection,
memory with saving on, emotions, spontaneous lines enabled, fake model and voice so the run
measures the application, not Ollama):

* 2,000 answered, 2,000 spoken, **never two voices at once** (`max_active == 1`);
* history 300 (its cap), immediate memory 40 (cap), feed index 600 (cap), diagnostics 20
  (cap), 772 viewers in RAM, 1,778 exchanges saved (orders aimed at the avatar are not);
* RAM growth over the second half: 1.9 MB, which is the per-viewer memory filling up to its
  bounds.

## Voice

Unchanged path. In the end-to-end run of the section 17 conversation with the real model
and a real voice (Piper *faber*), synthesis averaged 0.37 s per line. Real Kokoro voices
(pf_dora, pm_alex) pass the live tests.

## Overlay

Idle moods and lead reactions only change values the rig already blended every frame (no
new meshes, materials or render passes). The existing budget test (draw calls and
triangles for every character at high and low quality) still passes, and so does the GPU
resource release test.
