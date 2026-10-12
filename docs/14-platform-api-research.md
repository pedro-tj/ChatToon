# 14 — Platform API research (checked 2026-10-12)

What each platform officially allows for reading a live chat from a desktop app with no
server and no shipped secrets. Labels:

- **[docs]**: read in the official documentation at the URL given.
- **[live]**: observed against the real service from a development machine.
- **[unverified]**: memory, community sources or an inconsistent document.

| Platform | Level in ChatToon | Method | Login |
|---|---|---|---|
| YouTube | functional | public pop-out chat endpoints (as in 2.x), channel `/live` detection | none |
| Twitch | functional | EventSub WebSocket (official), or anonymous IRC | optional (Device Code) |
| Kick | experimental | public Pusher socket (unofficial); official webhooks as an option | optional (own app) |
| TikTok | experimental | TikTokLive library (unofficial) + Euler Stream signer | none |
| Facebook | limited | Graph API polling of `/{live-video}/comments` | own Meta app token |
| Instagram | limited | Graph API `live_media` + comments polling | own Meta app token |
| X | limited / unavailable | live video and Spaces: no API. Replies to a post: paid recent search | own bearer token |

## YouTube

Unchanged from 2.x (see `05-youtube.md`). New: `@handle`, `/channel/UC…`, `/c/…` and
`/user/…` targets. ChatToon fetches the channel's `/live` page, takes the canonical
`watch?v=` id, and waits (polling every 60 s) when there is no live [live: `@LofiGirl`
resolved and the chat was read].

## Twitch

- EventSub WebSocket `wss://eventsub.wss.twitch.tv/ws` [docs]:
  - Message types are welcome, keepalive, notification, reconnect and revocation.
  - The client must subscribe within 10 s of the welcome.
  - On `session_reconnect`, connect to the new URL first; the subscriptions move with it.
  - Clients may only send pongs.
  - Limits: 3 connections and 300 subscriptions per user token.
  - Only user tokens work over WebSocket.
  - <https://dev.twitch.tv/docs/eventsub/handling-websocket-events/>
- `channel.chat.message` v1 [docs]:
  - The condition is `{broadcaster_user_id, user_id}`, and only `user:read:chat` from the
    reading user is needed.
  - It works for any channel the user can read, up to 100 concurrent channels unless the
    user is a moderator there.
  - The same scope covers `channel.chat.notification` (subs, raids…),
    `channel.chat.message_delete` and `channel.chat.clear_user_messages`.
  - <https://dev.twitch.tv/docs/eventsub/eventsub-subscription-types/>
- Device Code Grant for **Public** clients [docs]:
  - The flow: `POST /oauth2/device`, then poll `POST /oauth2/token` with the
    `device_code` grant type.
  - No client secret is involved.
  - Refresh tokens are single use and expire after 30 days.
  - Tokens **must** be validated at start and hourly (`GET /oauth2/validate`).
  - Revocation is `POST /oauth2/revoke`.
  - Authorization Code with PKCE is not supported [docs + forum, 2024].
  - <https://dev.twitch.tv/docs/authentication/getting-tokens-oauth/>,
    <https://dev.twitch.tv/docs/authentication/validate-tokens/>
- IRC `wss://irc-ws.chat.twitch.tv:443` is "Active" on Twitch's product lifecycle page
  [docs]. The anonymous `justinfanNNNNN` login is not documented by Twitch (community
  knowledge), so the interface labels guest mode as such [live: messages, badges and ids
  read from `xqc`].
- Rate limits: 20 JOINs per 10 s; Helix uses a token bucket of about 800 points per minute
  with `Ratelimit-Reset` [docs].

## Kick

- OAuth 2.1 at `id.kick.com` [docs]:
  - PKCE is mandatory.
  - **`client_secret` is mandatory** for every grant, including `client_credentials`.
  - <https://docs.kick.com/getting-started/generating-tokens-oauth2-flow>
- Events (`chat.message.sent` and others) are delivered **only by webhook**, to the URL set
  once in the app settings; there is no WebSocket transport in the docs or changelog
  [docs].
  - Subscribe with `POST https://api.kick.com/public/v1/events/subscriptions`. App tokens
    may subscribe to any channel by broadcaster id.
  - <https://docs.kick.com/events/subscribe-to-events>
- Webhook security [docs]:
  - Signature: RSA PKCS#1 v1.5 SHA-256 over `"{message_id}.{timestamp}.{body}"`.
  - The public key comes from `GET /public/v1/public-key` and "can be rotated at any time".
  - <https://docs.kick.com/events/webhook-security>
- `GET /public/v1/channels?slug=` needs a token and returns no chatroom id [docs].
- **Conclusion:** the official path needs a secret and a public HTTPS endpoint, so it is an
  opt-in mode for streamers who have both. The default path is the Pusher socket that
  kick.com itself uses:
  - `wss://ws-us2.pusher.com/app/32cbd69e4b950bf97679`, channel `chatrooms.<id>.v2`.
  - The chatroom id comes from `kick.com/api/v2/channels/<slug>`.
  - It is unofficial; when Cloudflare blocks the lookup, the streamer can type the
    chatroom number. ChatToon never tries to get past the block.
  - [live: `absi`, 55 messages with moderator/subscriber badges in 45 s.]

## TikTok

- No official API exists for reading LIVE comments. TikTok for Developers lists Login Kit,
  Display, Research and others, but nothing for LIVE [docs]:
  <https://developers.tiktok.com/products/>
- TikTokLive 7.0.1 [source]:
  - License: "Modified AGPL-3.0". §18 allows overlay/bot integrations; §19 forbids
    commercial or hosted relay use.
  - Requires Python ≥ 3.10.
  - It is not packaged for Arch, and its `betterproto2==0.9.1` pin conflicts with Arch's
    0.10. Hence the private extras venv.
  - Each connection start calls **Euler Stream** (`api.eulerstream.com`). It sends the
    room id, a User-Agent and client name, and with them the user's IP address. The
    free tier allows about 2,500 requests a day.
  - The library creates the signer client with `verify_ssl=False`; ChatToon turns
    certificate verification back on (source option `sign_tls=library` restores the
    library default).

## Meta (Facebook and Instagram)

- Graph API v26.0, `GET /{live-video-id}/comments` [docs]:
  - Parameters: `filter=stream`, `order=reverse_chronological`, `live_filter`, `since`.
  - Commenter names come only with a **Page** token.
  - Permissions: `pages_read_engagement` / `pages_read_user_content`.
  - Public apps need App Review; apps in Development mode work for their own admins.
  - <https://developers.facebook.com/docs/graph-api/reference/live-video/comments/>
- `GET /{page-id}/live_videos` is documented inconsistently [unverified]. ChatToon tries
  it, and also accepts a pasted live-video link. Personal-profile lives cannot be read
  [docs: `user/live_videos` "Reading: You can't perform this operation"].
- Instagram [docs]:
  - `GET /{ig-user-id}/live_media` returns only lives broadcasting now.
  - `GET /{ig-media-id}/comments` returns at most 50 per call, top-level only.
  - The account must be professional and linked to a Page.
  - The `live_comments` webhook needs a public server and Advanced Access, so it is not
    used.
- Desktop OAuth:
  - The manual flow needs an embedded webview.
  - The app-secret exchange is server-side.
  - Device login does not state whether Page permissions are allowed.
  - Hence "bring your own app": the streamer pastes a token (Graph API Explorer → Access
    Token Debugger "Extend").
- Rate limits: Pages allow "4800 × engaged users / 24 h"; user tokens "200 × users / h".
  ChatToon reads `X-Business-Use-Case-Usage` / `X-App-Usage` and slows down above 75 %.

## X

- There are no endpoints for the chat of live video broadcasts. Spaces endpoints return
  metadata and shared posts, not chat [docs: <https://docs.x.com/x-api/spaces/introduction>].
  These targets are marked **unavailable**.
- Replies to a post: `GET /2/tweets/search/recent?query=conversation_id:<id>` [docs].
  - It needs the streamer's own developer app with a Bearer token.
  - Pricing in 2026 is pay-per-use, $0.005 per post read
    (<https://docs.x.com/x-api/getting-started/pricing>).
  - Limits: 450 requests per 15 min per app.
  - ChatToon polls every 20 s by default and skips the backlog with `start_time`, so old
    replies are never billed.
