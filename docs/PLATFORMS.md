# Streaming platforms

What each platform officially allows for reading a live chat from a desktop app with no
server and no shipped secrets, and how ChatToon does it. Research from 2026-10-12, updated
with live checks on 2026-10-17.

| Platform | Level | Method | Login |
|---|---|---|---|
| YouTube | functional | public pop-out chat endpoints; channel `/live` detection | none |
| Twitch | functional | EventSub WebSocket (official) or anonymous IRC (guest) | optional (Device Code) |
| Kick | limited | official webhooks with the streamer's own app; the unofficial public socket was retired by Kick | own app + public HTTPS |
| TikTok | experimental | TikTokLive library (unofficial) + Euler Stream signer | none |
| Facebook | limited | Graph API polling of `/{live-video}/comments` | own Meta app token |
| Instagram | limited | Graph API `live_media` + comments polling | own Meta app token |
| X | limited / unavailable | live video and Spaces: no API. Replies to a post: paid search | own bearer token |

## Live checks (2026-10-17, no credentials)

| Source | Result |
|---|---|
| YouTube `@LofiGirl` (channel → current live) | connected; 70–74 messages in 35 s, no duplicate ids, every message with an author |
| Twitch guest, `xqc` | connected; 28 messages in 45 s at the same time as YouTube (event-loop lag ≤ 2 ms) |
| Twitch guest, `lofigirl` | connected (no messages in that window) |
| Kick public socket (`absi`, `xqc`, `trainwreckstv`) | refused: Pusher `4001 App key … not in this cluster` on every cluster. Reported as `pusher-outdated` |

ChatToon does not try to discover kick.com's new key: that would be working around the
platform. The official webhook mode keeps working for streamers who have a Kick app and a
public HTTPS address.

## Connector contract (`core/streams/base.py`)

```python
class Connector:
    platform = "twitch"; support = "functional"
    reconnect_when_ended = False   # channel sources wait for the next live
    wait_poll = 60.0               # "live now?" interval while waiting

    async def session(self): ...   # one connection lifetime; return = live ended
    async def probe(self) -> ProbeResult: ...   # "Test connection", reads no messages
    async def close(self): ...
    # helpers: self.emit(msg), self.connected(name), self.retract(message_id, author_id)
```

`Connector.run()` is the single reconnection policy:

| Raised by `session()` | Status | What happens |
|---|---|---|
| returns | `ended` (`waiting` if `reconnect_when_ended`) | stop, or keep watching the channel |
| `NotLive` | `waiting` | sleep `wait_poll` (60 s; Meta 30 s), backoff reset |
| `RateLimited(retry_after)` | `reconnecting` | wait what the platform asked (5–900 s) |
| `TransientError`, network, odd payloads | `reconnecting` | exponential backoff with full jitter, cap 120 s, reset after 60 s connected |
| `AuthRequired` | `auth_required` | stop; the interface points to Accounts |
| `Unsupported` | `unsupported` | stop (missing optional library, no API) |
| `FatalError` / `LiveEnded` | `error` / `ended` | stop |

Each connector runs in its own task; a crash becomes `error/crashed` for that source only.
Messages are normalised to `ChatMessage` with `uid = "<source>:<id>"` (selection, feed,
moderation) and `key = "<platform>:<source>:<author id or name>"` (cooldowns, memory), so
"ana" on Twitch and "ana" on YouTube are different people.

## Selection and fairness (`core/messages.py`)

Modes: `smart` (default), `balanced`, `weighted`, `all`, `mentions`, `questions`,
`moderators`, `members`, `random`, `manual`.

* `balanced` / `weighted` use stride scheduling: each source advances by `1/weight` per answer
  and the one furthest behind goes next; a quiet source rejoins at the current time (no burst).
* `smart` with fairness adds `±(1/active − share_of_last_12)·5` (clamped ±2.5) to the score.
* A full queue evicts the weakest message of the **busiest** source.
* Paid messages go first; amounts are never compared across platforms.
* TTL drops old messages; evicted and expired ones are reported to the feed.

## Connectors

**YouTube** (`streams/youtube.py`, functional) — targets: a video/live URL (read until it
ends) or a channel (`@handle`, `/channel/UC…`, `/c/…`, `/user/…`, follows every live). Pop-out
chat polling at the server's pace; Super Chats/Stickers as `paid`; members. Probe: `live`,
`offline`, `chat-unavailable`, `not-found`.

**Twitch** (`streams/twitch.py`, functional) — option `mode`: `auto`, `account`,
`anonymous`. Account: Device Code flow with a Public app's Client ID, scope `user:read:chat`,
keyring `twitch/account`, hourly validation, single-use refresh tokens saved every time.
EventSub: `channel.chat.message`, `.notification`, `.message_delete`, `.clear_user_messages`.
Guest IRC (`justinfanNNNNN`, undocumented by Twitch and labelled as such). Bits → `paid`.

**Kick** (`streams/kick.py`) — option `mode`: `auto` (webhook if an app is configured, else
socket), `pusher`, `webhook`. Webhook (official): app token by `client_credentials`
(`streams.apps.kick_client_id` + keyring `kick/app`), subscribes `chat.message.sent` and
others, local receiver on `127.0.0.1:<kick_webhook_port>/kick/webhook`; body ≤ 64 KiB,
timestamp window −5/+1 min, RSA PKCS#1 v1.5 SHA-256 signature checked **before** parsing with
the key from `/public/v1/public-key`, duplicate ids ignored. Pusher (unofficial): retired by
Kick, see above.

**TikTok** (`streams/tiktok.py`, experimental, optional) — TikTokLive 7.0.1 in a private venv
(`chattoon extras install tiktok`; its `betterproto2` pin conflicts with Arch). Every
connection calls Euler Stream (`api.eulerstream.com`, ~2,500 free requests/day), which sees the
room id and the user's IP. The library disables certificate verification for it; ChatToon
turns it back on (`sign_tls=library` restores the library default).

**Facebook / Instagram** (`streams/meta.py`, limited) — keyring `meta/token`, pasted by the
streamer from their own Meta app (Page tokens derived from `/me/accounts` stay in memory and
are redacted). Facebook: Page (follows every live) or `video:<id>`; comments every 5 s with
`since`. Instagram: professional account linked to a Page, `live_media` + comments (≤ 50 per
call) every 6 s. Usage headers above 75 % slow polling ×3, above 90 % ×4. Personal profiles
cannot be read.

**X** (`streams/x.py`, limited/unavailable) — live video and Spaces have no chat API
(`unsupported/no-api`, no request made). Replies to a post through recent search with the
streamer's bearer token, every 20 s with `since_id`; the first query uses `start_time` so the
backlog is never billed.

## Official references

* Twitch EventSub WebSocket: <https://dev.twitch.tv/docs/eventsub/handling-websocket-events/>
* Twitch Device Code: <https://dev.twitch.tv/docs/authentication/getting-tokens-oauth/>
* Kick webhooks: <https://docs.kick.com/events/subscribe-to-events>, <https://docs.kick.com/events/webhook-security>
* TikTok for Developers (no LIVE API): <https://developers.tiktok.com/products/>
* Graph API live comments: <https://developers.facebook.com/docs/graph-api/reference/live-video/comments/>
* X Spaces: <https://docs.x.com/x-api/spaces/introduction>, pricing: <https://docs.x.com/x-api/getting-started/pricing>
