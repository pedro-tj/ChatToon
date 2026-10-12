# 15 — Multistream architecture

```
                         asyncio thread (Runtime)                                   Qt thread
┌───────────────────────────────────────────────────────────────────────────┐   ┌──────────────────┐
│ MultiStreamManager                                                        │   │ Backend           │
│  ├─ task: YouTubeConnector ─┐                                             │   │  ChatFeedModel    │
│  ├─ task: TwitchConnector  ─┤  emit(ChatMessage)  (platform, source_id,   │   │  (virtual list)   │
│  ├─ task: KickConnector    ─┼─► uid = "<source>:<id>", key per source)    │──►│  sources, accounts│
│  ├─ task: TikTokConnector  ─┤                                             │bus│  PlatformsPage    │
│  └─ task: Facebook/IG/X    ─┘                                             │   │  LiveChatPage     │
│                │                                                          │   └──────────────────┘
│                ▼                                                          │
│ ChatToonEngine._on_chat_message ─► MessageSelector (fair, bounded queue)  │
│                                        │ next()                           │
│ _work(): one message at a time ─► _converse() under _speech_lock          │
│      reading (with platform) ─► Ollama (platform in the prompt)           │
│      ─► TTS BigLinux / Kokoro ─► OverlayServer (bubble with "Twitch • Ana")│
└───────────────────────────────────────────────────────────────────────────┘
```

## Modules

| Module | Role |
|---|---|
| `core/streams/base.py` | `Connector` contract, the supervisor `run()` (reconnect policy), error taxonomy, `SourceStatus`, `ProbeResult`, `Backoff` |
| `core/streams/manager.py` | one task per source; live `configure()` / `connect()` / `disconnect()`; per-source counters; `probe()` |
| `core/streams/urls.py` | link/name recognition, canonical targets, duplicate keys. Parsing only, no network |
| `core/streams/{youtube,twitch,kick,tiktok,meta,x}.py` | connectors (see `16-connectors.md`) |
| `core/streams/__init__.py` | `PLATFORMS`: label, colour, glyph and the honest support level |
| `core/credentials.py` | Secret Service store (libsecret), 0600 file fallback, log redaction |
| `core/extras.py` | private venv for optional, unpackaged libraries (TikTokLive) |
| `gui/feed.py` | `ChatFeedModel` and `ChatFeedFilter`: the unified chat as a Qt model |

## Connector contract

```python
class Connector:
    platform = "twitch"; support = "functional"
    reconnect_when_ended = False   # channel-based sources wait for the next live
    wait_poll = 60.0               # "live now?" interval while waiting

    async def session(self): ...   # one connection lifetime: return = live ended
    async def probe(self) -> ProbeResult: ...   # "Test connection", reads no messages
    async def close(self): ...
    # helpers: self.emit(msg), self.connected(name), self.retract(message_id, author_id)
```

`Connector.run()` is the single reconnection policy:

| Raised by `session()` | Status | What happens |
|---|---|---|
| returns | `ended` (or `waiting` if `reconnect_when_ended`) | stop, or keep watching the channel |
| `NotLive` | `waiting` | sleep `wait_poll` (60 s; Meta 30 s), backoff reset |
| `RateLimited(retry_after)` | `reconnecting` | wait what the platform asked (clamped 5–900 s) |
| `TransientError`, network, HTTP errors, odd payloads | `reconnecting` | exponential backoff with jitter: `uniform(d/2, d)`, d = 2·2ⁿ, capped at 120 s. Reset after 60 s of stable connection |
| `AuthRequired` | `auth_required` | stop; the interface points to Accounts |
| `Unsupported` | `unsupported` | stop (missing optional library, no API) |
| `FatalError` / `LiveEnded` | `error` / `ended` | stop (bad channel, chat disabled) |

The manager runs every connector in its own task. A crash is caught there, reported as
`error/crashed`, and never reaches the other tasks. Late status reports from a cancelled
connector are ignored.

## Normalised message

`ChatMessage` gained `source_id`, `channel`, `event_type` (`message`, `paid`,
`subscription`, `gift`, `follow`, `raid`), `paid_kind` (`superchat`, `bits`, `kicks`,
`gift`…) and kept every 2.x field.

- `uid = f"{source_id}:{id}"`. Selection, approval, the feed and moderation all use it.
- `key = f"{platform}:{source_id}:{author_id or author}"`. Cooldowns, repetition and the
  AI's memory use it.
- `superchat` is the paid **label** ("R$ 10,00", "100 bits", "Rosa ×5"). Amounts are never
  compared across platforms.

## Selection and fairness

The modes are `smart` (default), `balanced`, `weighted`, `all`, `mentions`, `questions`,
`moderators`, `members`, `random` and `manual`. The 2.x modes keep their meaning.

- **balanced / weighted: stride scheduling.**
  - Each source has a virtual time that advances by `1/weight` per answer, and the source
    furthest behind goes next. Weight is the source's priority (1–5×) in `weighted` mode
    and 1 in `balanced`.
  - A source that was quiet rejoins at the current virtual time, so it gets its turn at
    once but no burst of saved-up turns.
  - Paid messages still go first.
  - Inside the chosen source, the smart score picks the message.
- **smart & co. with `fairness`:** a bonus of `±(1/active − share_of_last_12_answers)·5`
  (clamped to ±2.5) is added to the score.
- **Full queue:** the evicted message is the weakest one of the **busiest** source, so a
  YouTube flood never pushes Kick out.
- TTL drops old messages, so the avatar does not answer a topic the live has moved past.
  Expired and evicted messages are reported to the feed (`message_state: dropped`).
- **Favourite viewers** (`twitch:ana` or `ana`) get +3.
- **Events without text** (gifts, follows) are accepted only if `include_events` is on.

## One voice, always

Nothing changed in the speech path: `_work()` takes one message at a time, and
`_converse()` holds `_speech_lock` for the reading and the reply. Four platforms at once
produce four queued messages, not four voices. This is tested in
`test_engine_answers_four_platforms_one_voice_at_a_time` (`player.max_active == 1`).

## Platform in the reading, the prompt and the overlay

- **Reading** (`reading.py`): `reading.platform` is `never`, `multi` (default: only while two
  or more platforms are active) or `always`. The templates have Portuguese prepositions
  ("na Twitch", "do TikTok") and two or three variants chosen by `crc32(uid)`: varied over a
  live, stable for one message. The viewer's words are never changed.
- **Prompt** (`brain.py`):
  - The system prompt lists the platforms of the live. The list is stable while live, so
    Ollama's prefix cache stays valid.
  - Each message gets its platform label outside the `<<< >>>` data block.
  - A new rule says: never attribute to the viewer words they did not write.
- **Overlay:** reading events carry `platform`, `platformLabel`, `platformColor` and
  `paidKind`. The bubble shows a small pill built with `textContent` only. A colour is
  accepted only if it matches `^#[0-9a-f]{6}$`. `overlay.show_platform` turns the pill off.

## Live management

`Backend.addSource` / `updateSource` / `removeSource` save the settings and call
`engine.apply_settings()` → `streams.configure()`. While live, only the changed sources
restart, judged by a signature of (platform, target, options). The others keep their tasks.
`connectSource` / `disconnectSource` are temporary for the session: a "held" source stays
enabled but disconnected.

## GUI data flow

- `message` events are batched in an 80 ms timer and inserted with one `beginInsertRows`.
- The feed keeps at most 2,000 rows, dropping the oldest.
- `message_state` updates one row in O(1) through a uid → sequence map.
- The `ChatFeedFilter` proxy filters by platform, source, text and skipped rows.
- `sources` snapshots are coalesced to 4 per second; the queue to 10 per second.
- The QML `ListView` uses `reuseItems`, so only the visible rows exist.

## Settings

```json
"streams": {
  "sources": [{"id": "twitch-3fa2c1", "platform": "twitch", "target": "canal_linux", "label": "",
               "enabled": true, "priority": 1, "options": {"mode": "anonymous"}}],
  "apps": {"twitch_client_id": "", "kick_client_id": "", "kick_webhook_port": 8790},
  "migrated": true
}
```

- **Migration:** a 2.x file without `"streams"` gets its `chat.url` as source `youtube-main`.
  `chat.url` is kept for older versions.
- `Settings.stream_sources()` also covers unmigrated settings built in code.
- `SourceConfig.options` drops any key that looks like a credential (token, secret,
  password, cookie, key…), and `export_profile()` filters again.
