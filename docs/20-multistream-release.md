# 20 — Release 2.2.0 (multistream)

## What changed for the streamer

- **Streaming platforms** page (replaces "YouTube chat"): sources with live state, counters,
  test, connect/disconnect, edit and remove; selection rules; accounts; and the honest
  support sheet.
- **Live chat** page: every platform in one virtualized list, with search, filters and
  "Answer now".
- Fair attention between platforms: the `smart` fairness bonus, plus the `balanced` and
  `weighted` modes.
- Reading says where the message came from (Never / Multistream / Always). The OBS bubble
  shows "Twitch • Ana" (can be turned off).
- Logins in the system keyring; `chattoon extras install tiktok`; `chattoon doctor` lists
  the platforms.

## Compatibility

- **Settings:** a 2.x `settings.json` gets its `chat.url` as the source `youtube-main` on
  first load, and `chat.url` is kept. Nothing to reconfigure.
- **Profiles:** 2.x profiles import unchanged. New profiles include sources (without
  secrets) and public app ids.
- **Behaviour kept:**
  - the YouTube reader, its tests and its no-login method;
  - demo, assisted and automatic modes;
  - emergency stop;
  - one voice at a time;
  - the six characters and every TTS backend.
- **Intended changes:**
  - Message ids exposed to the interface and to `approve()` / `reject()` are namespaced by
    source (`"youtube-main:<id>"`).
  - Assisted mode now applies to every platform, not only YouTube.

## Packaging

| Item | Change |
|---|---|
| `pyproject.toml` | version 2.2.0; extras `kick-webhook` (cryptography), `keyring` (PyGObject), `tiktok` (TikTokLive==7.0.1, documented as installed via `chattoon extras`) |
| `PKGBUILD` | `pkgver=2.2.0`; new optdepends: `python-gobject`, `libsecret` (keyring), `python-cryptography` (Kick webhooks). **No new hard dependency** |
| Package data | new QML files are covered by the existing globs; the new package `chattoon.core.streams` is picked up by `packages.find` (checked by `test_wheel_contains_every_runtime_file`) |
| Desktop entry | comment and keywords mention multistream (`desktop-file-validate` passes) |
| Build | still offline: no download during `makepkg`. TikTokLive is never bundled and is installed only on request into `~/.local/share/chattoon/extras` |

## Licences of third-party pieces

| Piece | Licence | How it is used |
|---|---|---|
| TikTokLive 7.0.1 | Modified AGPL-3.0 (§18 allows overlay/bot integration) | optional, separate venv, not distributed with ChatToon |
| Euler Stream | third-party service | contacted by TikTokLive at each TikTok connection (disclosed in the interface) |
| cryptography, PyGObject/libsecret | Apache-2.0/BSD, LGPL | optional system packages |

## Needs credentials or real conditions (not verifiable here)

| What | Why it is not claimed as tested |
|---|---|
| Twitch EventSub with a real account | needs a registered Public app (Client ID) and an account login; covered by fake-server tests (welcome, subscribe, notifications, reconnect, revocation, refresh, revoke). `DEFAULT_CLIENT_ID` is empty until the project registers an app |
| Kick official webhooks | needs a Kick app with secret, a public HTTPS tunnel and a live channel; signature/replay logic tested with generated RSA keys |
| TikTok live comments | needs the optional library and a live TikTok profile; adapter tested against fakes and the real library's classes (no network) |
| Facebook / Instagram | need a Meta app, a Page / professional account, a token and a live; tested against fake Graph servers |
| X replies | needs a paid developer account; tested against a fake API |

Verified against the real services on 2026-10-12, reading public chats only with no
credentials, through the real `MultiStreamManager` at the same time:

- YouTube: `@LofiGirl` resolved to the live video, and messages were read.
- Twitch guest IRC (`xqc`): messages with ids, user ids and badges.
- Kick public chat (`absi`): 55 messages in 45 s, with moderator and subscriber flags.

## Known limitations

- Kick (default mode) and TikTok are unofficial and may break without notice. TikTok's free
  signing quota is about 2,500 connections a day.
- `GET /{page}/live_videos` on Facebook is documented inconsistently. If discovery fails,
  paste the live-video link.
- Instagram comments are capped at 50 per poll. On very busy lives, some can be missed
  between polls.
- The X recent search does not follow `next_token`, to limit cost: more than 100 replies
  in 20 s are partly skipped.
- Lip sync is volume-based, and speech starts after the whole reply is generated
  (unchanged).
