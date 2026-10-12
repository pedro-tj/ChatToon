# 18 — Security and authentication (multistream)

Builds on `09-security.md`. The new surface is network connectors, logins and one optional
local HTTP receiver.

## Logins

| Platform | Method | Scope / permission | Stored |
|---|---|---|---|
| Twitch | OAuth **Device Code Grant**, Public client: no secret, no password, no embedded browser | `user:read:chat` only | keyring `twitch/account`: access/refresh token, expiry, login, user id |
| Kick (webhook mode) | `client_credentials` with the streamer's own app | `events:subscribe` (app token) | keyring `kick/app`: client secret |
| Facebook / Instagram | token pasted from the streamer's own Meta app | read permissions listed in the UI | keyring `meta/token` |
| X | Bearer token pasted from the streamer's own developer app | app-only read | keyring `x/bearer` |
| TikTok | none (optional Euler Stream key) | — | keyring `tiktok/sign` |
| YouTube | none | — | — |

- ChatToon never asks for a password and ships no client secret. Public client ids live in
  `streams.apps` and are not secrets.
- Twitch tokens are validated at start and every hour, as Twitch requires. Refresh tokens
  are single use, so the new one is saved every time. Revocation sets the source to
  "Login required".
- "Disconnect" revokes the token at Twitch and deletes the local copy. "Delete from this
  computer" deletes any pasted secret.

## Storage

`core/credentials.py`:

- **Secret Service** through libsecret (`gi.repository.Secret`), schema
  `org.biglinux.ChatToon`. That is KWallet on Plasma, GNOME Keyring, or any compatible
  daemon.
- Calls can block on D-Bus or an unlock prompt, so they always run in worker threads,
  never on the Qt thread.
- With no keyring, credentials go to `~/.local/share/chattoon/credentials.json` with mode
  0600, written atomically. The interface shows that it is not encrypted.
- Settings files and exported profiles never contain credentials:
  - `SourceConfig.options` drops any key that looks like a credential;
  - `export_profile()` filters again;
  - tests check both.

## Logs and events

- `REDACTOR`, a `logging.Filter` on every root handler for the app and the CLI, masks two
  things:
  - every value ever stored in the credential store (and Meta Page tokens kept in memory);
  - patterns such as `access_token=…`, `Bearer …`, `OAuth …` and `oauth:…`.
- Connector errors and status details never include tokens. Tests for each connector run
  every failure path and check statuses, exceptions and log output.
- Overlay events carry only `platform`, `platformLabel`, `platformColor` and `paidKind`.
  `test_overlay_events_carry_platform_but_never_secrets` checks this.

## Network input

- **Pasted links:** `streams/urls.py` only parses them and never fetches them.
  - Only `http(s)` URLs of known hosts, or bare names matching each platform's charset,
    are accepted.
  - `javascript:`, `file:` and similar schemes are rejected.
  - Connectors call only their fixed hosts, overridable in tests through
    `ConnectorContext.extra`, so no SSRF is possible.
- **Viewer text:** cleaned by `clean_text` (control and bidi characters, length). It is
  shown as `Text.PlainText` in QML and `textContent` in the overlay, and kept inside the
  delimited data block in the prompt.
- **Overlay platform label and colour:** the label goes through `textContent` and is cut
  to 20 characters. The colour is accepted only if it matches `^#[0-9a-f]{6}$`; anything
  else uses a neutral fallback, tested in the headless browser.
- **Kick webhook receiver:**
  - It binds `127.0.0.1` only and never opens ports to the internet; the streamer chooses
    to forward a public HTTPS address.
  - Size limit 64 KiB, required headers, and a timestamp window of 5 min in the past and
    1 min in the future.
  - The RSA signature is checked **before** the body is parsed. The key is fetched from
    Kick, never hard-coded, and refreshed at most once a minute, so forged requests cannot
    make ChatToon hammer Kick.
  - Duplicate message ids are ignored.
- **TikTok:** TikTokLive disables certificate verification for Euler Stream; ChatToon
  turns it back on. The Euler key is passed per client, never through the library's global
  default.

## Platform terms and pacing

- No CAPTCHA, login or Cloudflare circumvention:
  - When kick.com blocks the chatroom lookup, the source stops and asks the streamer to
    paste the number.
  - Guest Twitch IRC is the anonymous read-only mode Twitch's servers offer; it is
    labelled as undocumented.
- Backoff is exponential with full jitter (cap 120 s). `Retry-After`, `Ratelimit-Reset`,
  `x-rate-limit-*` and Meta usage headers are honoured.
- "Not live" checks are slow (60 s, Meta 30 s). Revoked logins and missing apps stop the
  source instead of retrying.
- Unofficial methods (Kick Pusher, TikTokLive) are shown as **experimental** with their
  risks, and are never required by the rest of the application.
