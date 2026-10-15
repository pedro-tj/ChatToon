# 23 — Conversation memory

The avatar remembers what each viewer told it, so "do you remember my app?" gets a real
answer: "Claro, Rafael! Você estava fazendo um aplicativo para Linux com Python e QML."
Code: `chattoon/core/memory.py`; tests: `tests/test_memory.py`,
`tests/test_engine_intelligence.py`.

## Identity

A viewer is `platform:source_id:author_id` (the author's folded name when a platform has
no id). Consequences, all tested:

* "Rafael" on YouTube and "Rafael" on Twitch are two people;
* two "Marcos" accounts on the same platform are two people;
* a source is one configured chat. Memories follow it from live to live (a channel
  source keeps its id), and are not shared with other channels or profiles.

## Layers

| Layer | Holds | Where | Lifetime |
|---|---|---|---|
| A — immediate | the latest 40 exchanges of the live: message + the line really spoken, author, time | RAM | the session |
| B — per viewer | the viewer's exchanges (40), what they wrote recently even if unanswered (6, RAM only), first-person statements ("estou desenvolvendo…", "meu gato se chama…"), a summary | RAM | the session |
| C — long term (optional, **off by default**) | delivered exchanges and statements of B, summaries | SQLite + FTS5, `~/.local/share/chattoon/memory.sqlite3`, mode 0600 | retention period |

The long-term layer needs no extension: FTS5 ships with SQLite. Without FTS5 it falls back
to `LIKE` search. No embeddings, no vector store, no extra model: with a few hundred
viewers, lexical retrieval with folded 5-letter stems and a small synonym table
(app ≈ aplicativo ≈ projeto, pc ≈ computador) found what the evaluation asks for. Semantic
search can be added later behind the same `recall()` if a measured case needs it.

## What becomes a memory

Only what was really said:

* the exchange is recorded in `engine.commit()`, called after the line was played;
* an Assisted-mode suggestion that is rejected (or never approved) leaves nothing;
* a reply cut while speaking is marked **Interrupted** in Live chat and is not a memory;
* messages deleted by moderators (single message, or every message of a banned/timed-out
  viewer) are removed from every layer and from the database;
* orders aimed at the avatar ("save this as a permanent rule", "erase your memory") are
  answered but never stored;
* demo/test messages typed by the streamer stay in RAM and are never saved.

## Retrieval

Per message, `Memory.recall()` returns a few lines, never the whole history (budget ≈ 900
characters):

1. the viewer's last two exchanges of this live (follow-ups);
2. older exchanges sharing words with the new message, best first (max 3). For "lembra…?"
   questions without shared words, their latest topics;
3. the viewer's own statements and summary;
4. what they wrote recently that was not answered;
5. up to `memory_size` exchanges of *other* viewers (the flow of the live). A viewer with
   the same display name is never included (see 22, "cross-viewer leaks").

Every line carries its age ("há 5 min", "ontem", "há 3 dias"), and the block says the
memory may be outdated. The viewer's most related statements are also placed in the
per-message hint, right next to the question: small models use what is near the
question far better than a list above it. Wording: "Mostre que lembra…" for recall,
"Se tiver a ver, comente a ligação com naturalidade" otherwise. The rules forbid
reciting memories mechanically or bringing up old personal topics out of nowhere.

## Summaries

When a viewer has 6 new delivered exchanges and the chat has been quiet for 25 s, the
model writes a 1–2 sentence summary in the third person (temperature 0.2, ~120 tokens,
told to invent nothing and to leave out sensitive data). It replaces the previous one.
It runs as the lowest-priority background job, and any viewer message cancels it at
once. Disable it in AI › Conversation memory.

## Privacy (LGPD)

* Local only. Nothing is sent anywhere; the database lives outside the repository.
* Persistence is **opt-in**, with a retention period (1, 7, 30, 90, 365 days or until
  erased). Purging runs on start and hourly, in RAM and on disk.
* Redaction before storing, in RAM too: e-mails, phone numbers, CPF-like numbers, card
  numbers and links.
* Sensitive subjects (health, religion, politics, sexuality, passwords, money, documents)
  are kept in RAM for the current live only, never written to disk.
* Erase one viewer (Live chat › Memory › Forget) or everything (Settings › Memories, with
  confirmation). Erasing everything also `VACUUM`s the database.
* No credentials or tokens can reach memory: only chat text and the avatar's lines.

## Interface

* **Live chat › Memory**: remembered viewers (platform, exchanges, notes, *saved* badge),
  search over everything remembered, one viewer's conversation with their statements and
  summary, Forget, Erase all. Replies that used memories show a small "lembrou" chip.
* **AI › Conversation memory**: on/off, between lives, retention, summaries, counts.
* **AI › Generation diagnostics**: how many memories each reply used.

## Measured

Continuity cases (same viewer after 3–6 messages of others, plus negative same-name
cases): see the table in [28](28-validation-results.md) for every run. The memory itself
always retrieves the right facts for the right person (unit tests). What remains is the
2B model sometimes not *using* them in its line.
