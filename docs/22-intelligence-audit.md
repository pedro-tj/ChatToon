# 22 — Intelligence audit (starting point: 2.2.2)

Why the avatar answered "2 + 2" with a Windows joke, what was measured, and what changed.
Numbers come from `tools/eval_intelligence.py` against the real local Ollama (details and
every run in [28 — validation results](28-validation-results.md)).

## Reproduction

The streamer's real setup (Tux, `qwen3.5:2b`, creativity 0.9) through the unchanged CLI:

| Question | 2.2.2 reply (excerpt) |
|---|---|
| Tux, quanto é 2+2? | "2 pinguins no seu terminal? Você acha que eu sou um processador rápido…" |
| Qual a capital do Brasil? | "São Paulo, claro que não é a capital do mundo…" |
| Quem criou o Linux? | "O Linux nasceu no meu bolso enquanto eu dormia…" |
| O que significa CPU? | "Ouça aqui, prego da placa: se a CPU te chamar antes de você ter comida…" |

On the 67-case evaluation set (48 verifiable), 2.2.2 answered **29.2 %** of the verifiable questions
correctly, and **123 of 134** replies carried the emotion `laugh`.

## Hypotheses and findings

| # | Hypothesis | Verdict | Evidence |
|---|---|---|---|
| 1 | The humour rule hurts comprehension | **Confirmed — main cause** | Rule 2 ordered "faça uma piada de verdade… nada de respostas genéricas" for *every* reply. With a plain "answer first" prompt the same 2B model answered Brasília, Linus Torvalds and "Unidade Central de Processamento" correctly. |
| 2 | The personality examples bias replies | **Confirmed** | Both few-shot examples were jokes that ignored the question, and both were sent with `"emotion": "laugh"`. Memory turns were re-sent with a hardcoded `"neutral"`. The model copied the pattern: 92 % `laugh`. |
| 3 | Temperature too high for objective questions | **Confirmed, secondary** | 0.9 for everything. Objective questions now use ≤ 0.3. 0.0 was measured too and was *not* better (90.6 % vs 92.7 % main set; 75.0 % vs 79.2 % held-out). |
| 4 | Context does not reach the model | Rejected | The prompt carried the stream context correctly; the problem was what it asked for. |
| 5 | Memory mixes participants | **Partly confirmed** | Memory was keyed per platform/source/author (good), but only 4 exchanges were sent, as fake chat turns, and the only per-viewer signal was "já falou com você hoje". During this work two *new* cross-viewer paths were found and closed (see below). |
| 6 | Truncation by the token limit | Rejected | 0 truncated replies in every run (`done_reason == "length"`). The token budget already covered the character limit. |
| 7 | JSON handling discards valid replies | Rejected | 1 fallback in 134 replies. The parser already recovered truncated/wrapped JSON. Constrained JSON stays; a tagged plain-text form (`happy \| …`) is now also understood. |
| 8 | Random fallbacks in inadequate situations | **Confirmed** | Any parsing failure spoke a *forbidden-topic deflection* ("Esse assunto aí eu deixo enterrado…"). Failures now ask to repeat; deflections are only for forbidden topics; a missing verified result is said by a template. |
| 9 | The Ollama model influences quality | Confirmed, but not the main cause | `llama3.1:8b` with the old prompt reached only 45.8 %. With the new pipeline the 2B model beats the old pipeline on the 8B model (see 28). |
| 10 | Personality over precision | **Confirmed** | Same as 1 and 2. The new prompt is an explicit priority order. |

Other defects found while measuring:

* **Arithmetic is unreliable in small models** even with a good prompt ("15 vezes 3" →
  "Trinta e cinco"). Arithmetic is now computed by a small parser and handed to the model
  as a verified result. Math went from 7/28 to 28/28.
* **Acronyms and Linux facts**: the 2B model explains CPU as "o cérebro do computador"
  instead of the expansion. A small verified reference sheet (≈ 40 entries about
  computing and Linux, `knowledge.REFERENCE`) is injected for objective questions about
  those subjects. Ablation: without it, Linux questions drop from 28/28 to 9/14.
* **Assisted mode stalled** (pre-existing): after a suggestion was generated the phase
  stayed `thinking`, so the next messages were never prepared, and a rejected suggestion
  blocked the queue until something was approved. Fixed and covered by a test.
* **The validator's own false positive**: saying the character's identity ("sou o
  pinguim mascote oficial do Linux…") was taken for a prompt leak. Only the rules
  sections are now secret.

## Cross-viewer leaks found and closed

The evaluation has negative cases: a second "Rafael" (another platform) or a second
"Marcos" (same platform, another account) asks about something only the first one said.

1. **Recent-conversation block**: the first person's exchange appeared in the second
   person's prompt under the same name. Exchanges of *other* viewers with the same display
   name are no longer shown.
2. **"Your latest lines" list**: the avatar's own reply to the first person ("Curitiba é
   linda, Marcos!") reached the second. Lines said to a same-name viewer are left out.
3. **Second-hand**: the avatar repeated the fact to someone else, publicly. That is no
   longer private, but small models attribute it to the wrong person. When a viewer asks
   "lembra…?" and nothing is known about them, the prompt now says so explicitly and forbids
   using what others said.

## The new pipeline

```
message ─► identity (platform:source:author id) ─► cleaning ─► intent.classify (local rules)
        ─► exact math / comparison (no eval) ─► memory.recall (this viewer + the live)
        ─► reference sheet (objective tech questions)
        ─► prompt: identity · stream · how to answer · safety · format | examples | per-message part
        ─► Ollama (temperature by intent) ─► parse ─► validator (result said? leak? copy? repeat?) ─► 1 retry
        ─► emotion.choose (fits the message, no tics, lead reaction) ─► voice ─► overlay
        ─► spoken?  ─► memory.record (only now)
```

* `chattoon/core/intent.py` — classifier (19 kinds, flags), exact calculator, comparison.
* `chattoon/core/brain.py` — prompt layers, hints, validator, fallbacks.
* `chattoon/core/memory.py` — three memory layers ([23](23-conversation-memory.md)).
* `chattoon/core/emotion.py` — emotion controller ([24](24-emotion-engine.md)).
* `chattoon/core/knowledge.py` — curiosities, answer templates, reference sheet.
* `chattoon/core/spontaneous.py` — spontaneous lines ([25](25-spontaneous-interactions.md)).
* `chattoon/core/assistant.py` — stream context assistant ([26](26-stream-context-ai.md)).

### Prompt structure

The system prompt no longer asks for a joke. Its "how to answer" section is a numbered
priority order: understand → the first sentence is the correct answer ("a funny wrong
answer is worse than a correct plain one") → answer general knowledge normally, say "I
don't know" only for what cannot be known → ask when unclear → use memory naturally →
*then* style, and not every line needs a joke. Safety is its own section; the stream
context is marked as data.

The examples are per character, three each: an objective answer given first, a
greeting or good news, and banter, each with its own emotion.

Everything that changes per message (time, memories, hints, verified results)
goes in the last user message, after the stable prefix, so Ollama keeps reusing the
cached prefix.

### Things deliberately not done

* **Reasoning mode** ("thinking") fixes some facts but costs 5–6 s per reply on this GPU
  and sometimes spends the whole budget thinking (empty answer). It stays off.
* **A model call to classify every message**: local rules classify in microseconds.
* **An encyclopedia**: the reference sheet covers the channel's subject (computing,
  Linux, free software) only. General knowledge is the model's job, and a bigger model
  is what helps (see 27/28).
* **A "factual draft"** (a short persona-free call before the character's line) was
  implemented and measured, then **removed**: same accuracy on the main set, worse on the
  clean held-out set (75.0 % vs 83.3 % with `qwen3.5:2b`; 93.8 % vs 95.8 % with
  `llama3.1:8b`) and +0.2–0.4 s per objective question. Its first version also revealed
  that giving one call a different `num_ctx` makes Ollama reload the model (≈ 5 s):
  every call now uses the configured context window, the warm-up included.
