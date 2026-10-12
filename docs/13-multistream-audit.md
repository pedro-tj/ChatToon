# 13 — Multistream audit (starting point: 2.1.0)

Record of what had to change for ChatToon to read several platforms at once. Nothing
here is needed to run the application.

## Message path in 2.1

```
LiveChatClient (youtube_chat.py)          one task, created in ChatToonEngine._start_chat()
  └─ on_message ─► ChatToonEngine._on_chat_message ─► MessageSelector.offer()
                                            └─ _work() loop ─► selector.next() ─► _answer()
                                                 └─ _converse(): reading ─► Ollama ─► TTS ─► overlay
```

`_speech_lock` already guaranteed one voice at a time, and `_converse` already overlapped
the reading with the reply's generation. Those parts were kept as they were.

## Single-platform assumptions found

| Where | Assumption | Consequence for multistream |
|---|---|---|
| `config.ChatSettings.url` | one YouTube URL | no place for a second chat |
| `engine._chat_task`, `chat_status` | one task, one status | one failure = "the chat" failed |
| `engine.start()` | refuses to start without `chat.url` | blocks non-YouTube setups |
| `engine._answer()` | `msg.platform == "youtube"` decides assisted mode | other platforms would bypass approval |
| `messages.ChatMessage.key` | `author_id or author` | "ana" on Twitch and on YouTube = same person (shared cooldown) |
| `MessageSelector._reject_reason` | dedup by bare `id` | two platforms with id `"1"` collide |
| `MessageSelector._score` / `next` | no notion of source | the busiest chat wins every turn |
| `queue full` eviction | worst score overall | a YouTube flood pushes small chats out |
| `brain.memory` / "talked to you earlier" | compares author names | cross-platform confusion in the prompt |
| `reading.py` templates | "Super Chat" is the only paid kind | Bits/Kicks/gifts would be called Super Chat |
| `gui/backend.validateUrl`, `ChatPage.qml` | YouTube-only form | no way to add other chats |
| `backend.messages` (JS array, 120 items) | rebuilt and re-rendered per message | does not scale to multistream rates |
| overlay `speak` event | no origin | the bubble cannot say where a message came from |
| `cli doctor` | YouTube implicit | no view of other sources |

## Things that already fit and were reused

- `Runtime`: the asyncio loop in its own thread. Every connector is a task there and the Qt
  thread is never blocked.
- `EventBus` → `Backend._event` queued signal: thread-safe delivery to the GUI.
- `LiveChatClient`: reused as is, wrapped by `YouTubeConnector`. Its tests still pass
  unchanged.
- `clean_text`, mention detection, TTL, cooldown and the age bonus against starvation.
- `Brain._wrap`: viewer text stays in a delimited data block. The platform name is added
  outside that block.
- `OverlayServer`: one-way, token-guarded and bound to 127.0.0.1. Only new optional
  event fields were added.

## Compatibility constraints

- `settings.json` from 2.x must keep working without any action from the streamer.
- Profiles exported by 2.x must still import.
- Tests from 2.1 must keep passing. Only two changed: they now approve a message by its
  source-namespaced id (`"youtube-main:yt1"`), which is the intended behaviour change.
