# 25 — Spontaneous lines

When the chat is quiet, the avatar can speak up on its own, like a co-host: "Ué, cadê todo
mundo? Estão compilando o kernel ou foram buscar café?". Off by default (Settings ›
Spontaneous lines). Code: `chattoon/core/spontaneous.py`, `knowledge.py`,
`engine._idle_turn()`.

## Priority

```
emergency stop / interrupt  >  streamer commands (test, say, approve)  >  paid & priority messages
  >  chat replies  >  spontaneous lines  >  memory summaries
```

* A spontaneous line is only considered when the engine is **live** (`running`), idle,
  with an empty queue and no suggestion waiting. Never paused, stopped, after an emergency
  stop, or in Assisted mode (where nothing is said without approval).
* The chat must have been quiet for `min_idle` seconds (default 90): any viewer message,
  even one that was not queued, counts as activity. Lines are spaced by `min_interval`
  (default 240 s). "Rarely" multiplies both by 1.8, "Often" by 0.55. Optional quiet hours
  (e.g. 23:00–07:00, across midnight).
* **A viewer cancels a line still being prepared** (model writing it or voice being
  rendered). A line already being *spoken* finishes: it is one or two short sentences,
  and the speech lock guarantees no overlap. The viewer's reply comes right after. This is
  the "soft and predictable" interruption.
* Emergency stop and interrupt cancel it like any reply. Shutdown cancels and awaits the
  worker.

## What it says

| Category | Source | Model? |
|---|---|---|
| Invitations to talk | character bank (`knowledge.BANK`) | written lines, or varied by the model half of the time |
| Curiosities | character bank: **facts** (checked) and **fiction** (the character's lore), plus the streamer's own lines | never — facts are spoken exactly as written |
| Comments on the topic | Stream context › topic/description | written by the model; without the model a template ("O assunto de hoje é…") |
| Humour, funny thoughts | character bank | written lines or the model |
| Catchphrases | the character's and the channel's catchphrases | no |
| Calls to action | Stream context › calls to action (off by default here) | no |

Model-written lines are told not to state facts, numbers, news or channel information,
and not to name viewers. A line containing digits, "você sabia", "segundo", "estudos"…
is rejected, and a written line of the same kind is used. If the model is down, written
lines are used.

Anti-repetition: never the same category twice in a row, and a line comes back only
after every other line of its kind was said (least recently used first).

Each character has 4–10 checked facts (penguins, worms, owls, cats, dogs, space, Linux
history), clearly separated from fiction (`kind` = `fact` / `fiction`, shown in
Characters › Curiosities). Streamers add their own lines there, one per line. They are
spoken as written, so the interface reminds them to check what they claim.

## Face and body

Invitations use the generic `lookAround` gesture, reflections `curious`, curiosities a
short `thinking` lead before `happy`, humour `laugh`, catchphrases `celebrate`. The
"Energy" setting scales intensity; "calm" drops the gestures. Idle moods
([24](24-emotion-engine.md)) run between lines.

## Testing it

* "Try one now" (Settings) and a ▶ per category; "Try a spontaneous line" (Characters).
  It works whatever the mode, even before going live.
* `tests/test_engine_intelligence.py`: speaks when quiet (demo); silent when disabled,
  paused, after an emergency stop and in Assisted mode; a viewer cancels a line being
  prepared and is answered first, with never two voices at once; model failure falls
  back to a written invitation; the test button works while not live.
* `tests/test_intelligence.py`: timing, quiet hours, rotation, facts never rewritten,
  model lines with facts rejected, categories without a source.
