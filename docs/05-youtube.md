# 05 — YouTube Live chat (`core/youtube_chat.py`)

## How it reads

The same public endpoints the chat pop-out window uses: `GET /live_chat?is_popout=1&v=ID`
(InnerTube key, client context, first continuation, backlog) and then
`POST /youtubei/v1/live_chat/get_live_chat` with the continuation, waiting the `timeoutMs`
the server asks for (clamped to 1–10 s). That is the polling rate of an open chat window — not
more aggressive. No login, no API key, no quota.

## Links accepted

`watch?v=ID`, `/live/ID`, `youtu.be/ID`, `live_chat?v=ID`, `live_chat?is_popout=1&v=ID`,
`m.youtube.com`, `studio.youtube.com/video/ID/...` and a bare 11-character id. Anything else
is rejected with a message.

## Data per message

| Field | Source |
|---|---|
| id | `liveChatTextMessageRenderer.id` (de-duplication key, LRU of 5 000) |
| author, channel id | `authorName.simpleText`, `authorExternalChannelId` |
| text | `message.runs` (standard emoji kept, channel emotes dropped) |
| timestamp | `timestampUsec` |
| moderator / owner / verified | `authorBadges[].icon.iconType` |
| member | badge with `customThumbnail`, or membership item |
| Super Chat / Sticker | `liveChatPaidMessageRenderer` / `liveChatPaidStickerRenderer` → `purchaseAmountText` |

Placeholders, system notices, deletions and other action types are ignored.

## Robustness

- Backlog present at connection time is marked as seen, never answered (configurable).
- Network errors → reconnect with exponential backoff (2, 4, 8 … 60 s), status shown in the UI.
- `ChatError` (not live, chat disabled, members-only, ended) is reported with YouTube's own
  message (e.g. "O chat está desativado para esta transmissão ao vivo.").
- No continuation → "chat ended". Cancelling the task stops cleanly.

## Validation

Unit tests with a local fake YouTube server (parsing, dedup, backlog, reconnect, end, disabled
chat, cancel) and a live test (`--run-live`, `CHATTOON_LIVE_URL`): on 2026-10-11 a public news
live delivered 9 new messages in 25 s, all with id, author and timestamp, no duplicates.

If YouTube changes the page format, `parse_page` raises a clear `ChatError` instead of failing
silently.

## Selection (`core/messages.py`)

Modes: smart, all, mentions, questions, moderators, members, random, manual. Smart scoring adds
points for mentions of the avatar, questions, moderators, members and Super Chats (highest),
plus an age bonus up to the message TTL so nobody starves. Per-viewer cooldown (Super Chats
bypass it), queue limit (drops the lowest score), TTL, blocked words, `!commands`, and a
30-second same-text repeat filter.
