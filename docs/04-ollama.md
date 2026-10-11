# 04 — Ollama integration (`core/ollama.py`)

Uses the HTTP API of the installed Ollama (validated against 0.33.3): `/api/version`,
`/api/tags`, `/api/show` (capabilities), `/api/pull` (streamed progress), `/api/generate`
(preload) and `/api/chat` (streaming).

- **Host** configurable (default `http://127.0.0.1:11434`); never changes Ollama's config.
- **Models**: lists installed chat models (embedding models hidden). The first time, the
  first installed model from the suggestion list is selected; nothing is assumed to exist.
  Suggestions (verified in the Ollama registry): `gemma3:4b`, `qwen3.5:4b`, `qwen3:4b`,
  `llama3.2:3b`, `gemma3:1b`, `qwen3.5:2b`.
- **Structured replies**: `format` with a JSON schema `{say, emotion, intensity}`; the reply
  is still validated in `brain.parse`.
- **Thinking models** (capability `thinking`, e.g. Qwen 3.x) get `think: false`.
- **Options**: temperature, `num_predict`, `num_ctx`, `keep_alive`; timeout per reply;
  cancelling the task closes the stream (interrupt / emergency stop).
- **Errors** are typed: `OllamaUnavailable`, `ModelNotFound`, `OllamaError` (empty answer,
  stream error, HTTP error, timeout) and shown to the user; the avatar never speaks raw chat
  text instead.
- **One generation at a time** — the engine processes a single message.
- **Warm-up**: on Start the model is preloaded and the Piper voice prewarmed.

## Measured latency (GTX 1050 Ti 4 GB, `gemma3:4b` Q4_K_M)

| | before | after |
|---|---|---|
| 5 sequential replies | 7.4 → 13.5 s (growing) | 8.2 → 9.2 s (flat) |

Breakdown of one reply: ~0.8–1.1 k prompt tokens evaluated in 3–7 s, ~45 tokens generated at
~21 tok/s (~2 s). The growth came from putting the clock and the latest replies inside the
system prompt; they now travel with the last message, keeping the system prompt identical.

**Limitation found:** with this Ollama, `gemma3` reuses the KV cache only for identical
requests, so the shared prefix is re-evaluated every time (likely due to Gemma 3's
sliding-window attention). `qwen3.5:0.8b` reused the prefix (0.9 s instead of 6 s) in the same
test. A Qwen-family 4B model should therefore answer faster on this GPU; this was not measured
because only `gemma3:4b` was downloaded. Lower *Conversation memory* to shorten prompts, and
keep a single model loaded (a second model competes for the 4 GB of VRAM).
