# 16 — Connectors reference

Every connector's base URLs can be overridden through `ConnectorContext.extra`, which is
how the tests point them at local fake servers. Credentials are read from the keyring in a
worker thread and never logged.

## YouTube — `streams/youtube.py` (functional)

| | |
|---|---|
| Targets | video/live URL (read until it ends, like 2.x) · `@handle`, `/channel/UC…`, `/c/…`, `/user/…` (follows every live) |
| Method | `LiveChatClient` from 2.x (pop-out chat, server-paced polling) · channel `/live` page → canonical `watch?v=` |
| Events | messages, Super Chats / Super Stickers (`paid`), members |
| Probe | `live`, `offline` (channel exists, not live), `chat-unavailable`, `not-found` |

## Twitch — `streams/twitch.py` (functional)

| | |
|---|---|
| Option `mode` | `auto` (account if connected, else guest) · `account` · `anonymous` |
| Account | Device Code flow with a **Public** app's Client ID (`streams.apps.twitch_client_id`, or `DEFAULT_CLIENT_ID` if the project registers one). Scope `user:read:chat`. Keyring key `twitch/account` |
| EventSub | `channel.chat.message`, `channel.chat.notification` (sub, resub, gifts, raid), `channel.chat.message_delete`, `channel.chat.clear_user_messages`. Session reconnect keeps the subscriptions. Keepalive timeout + 5 s; hourly validation; refresh with token rotation; revocation → `auth_required` |
| Guest IRC | `CAP twitch.tv/tags twitch.tv/commands`, `NICK justinfanNNNNN`. `ROOMSTATE` = joined. PRIVMSG/USERNOTICE mapped; CLEARMSG/CLEARCHAT → retract; PING/PONG; `RECONNECT` handled |
| Paid | Bits → `paid`, `paid_kind=bits`, "250 bits" |
| Probe | account: validate + resolve the channel. Guest: join and wait for `ROOMSTATE` (only existing channels send it) |

## Kick — `streams/kick.py` (experimental by default)

| | |
|---|---|
| Option `mode` | `auto` (webhook if a Kick app is configured, else pusher) · `pusher` · `webhook` |
| Option `chatroom_id` | digits; skips the lookup when kick.com blocks it |
| Pusher (unofficial) | chatroom id from `kick.com/api/v2/channels/<slug>`. Subscribe `chatrooms.<id>.v2`. `pusher:ping`/`pong` keepalive. Errors 4000–4099 fatal, 4100–4299 retry. `ChatMessageEvent` → message (`[emote:ID:name]` → name). Delete/ban events → retract |
| Webhook (official) | app token via `client_credentials` (`streams.apps.kick_client_id` + keyring `kick/app` `{client_secret}`). Subscribes `chat.message.sent`, subscriptions, `kicks.gifted`, `moderation.banned` and deletes them on close. Local receiver **127.0.0.1 only** at `kick_webhook_port`, path `/kick/webhook`. Checks: body ≤ 64 KiB, headers, timestamp window (−5 min / +1 min), RSA PKCS#1 v1.5 SHA-256 signature with the key from `/public/v1/public-key` (refetched at most once a minute on failure), duplicate ids. One shared receiver per port, dispatched by broadcaster id |
| Paid | `kicks.gifted` → `gift`, `paid_kind=kicks` |

## TikTok — `streams/tiktok.py` (experimental, optional)

| | |
|---|---|
| Requires | TikTokLive 7.0.1 in `~/.local/share/chattoon/extras` (`chattoon extras install tiktok`). Without it: `unsupported/missing-dependency` |
| Keyring | `tiktok/sign` `{api_key}` (optional Euler Stream key, passed per client, never global) |
| Option `sign_tls` | `verify` (default: certificate verification forced on for Euler Stream) · `library` |
| Flow | `is_live()` (TikTok only, no Euler quota) → `start(process_connect_events=not skip_backlog, fetch_live_check=False)`. Stop with `disconnect()` + `web.close()` (never `close()` / `run()` inside our loop) |
| Events | `CommentEvent` → message (moderator/subscriber/host flags) · `GiftEvent` at the end of a streak → `gift` "Rosa ×5" · `FollowEvent` · `SubNotifyEvent`. Likes/shares/joins ignored |
| Errors | offline → waiting · not found / age restricted → error · signature rate limit → `RateLimited` · sign/blocked/network → retry |

## Facebook and Instagram — `streams/meta.py` (limited)

| | |
|---|---|
| Keyring | `meta/token` `{access_token, kind?}`, pasted by the streamer (their own Meta app). Page tokens derived from `/me/accounts` stay in memory and are registered for log redaction |
| Facebook targets | Page (name/id, follows every live: `/{page}/live_videos?broadcast_status=["LIVE"]`) or `video:<id>` (that live only) |
| Facebook comments | `/{live}/comments?filter=stream&order=reverse_chronological&live_filter=no_filter&since=…`, default every 5 s (option `poll`, 3–60) |
| Instagram | professional account linked to a Page: `/{ig-user}/live_media`, `/{media}/comments` (≤ 50, de-duplicated), default every 6 s |
| Rate limits | `X-Business-Use-Case-Usage` / `X-App-Usage`: above 75 % → ×3 interval, 90 % → ×4; throttling codes → `RateLimited` with `estimated_time_to_regain_access` |
| Errors | 190 & co. → `auth_required`; permission errors name the permission; personal profiles → `unsupported` |

## X — `streams/x.py` (limited / unavailable)

| | |
|---|---|
| `broadcast:<id>` | `unsupported/no-api`: there is no chat API for live video or Spaces. No request is made |
| `post:<id>` | replies via `/2/tweets/search/recent?query=conversation_id:<id>` with keyring `x/bearer` `{bearer_token}`. Every 20 s by default (option `poll`, 15–300) with `since_id`. The first query uses `start_time` so the backlog is never billed. Follows `x-rate-limit-*` headers. 402/403 billing → `plan-required` |
