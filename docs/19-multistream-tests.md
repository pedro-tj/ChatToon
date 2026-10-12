# 19 — Multistream tests

Run everything with `python -m pytest`. All tests use local fakes: aiohttp servers on
127.0.0.1, fake TTS/Ollama/player and an in-memory credential store
(`CHATTOON_CREDENTIALS=memory` is forced in `tests/conftest.py`, so tests never touch the
real keyring).

## New test files

| File | Tests | Covers |
|---|---|---|
| `test_streams_core.py` | 28 | URL detection (valid/invalid/short links/schemes/ambiguous), 2.x migration, secret-free options and profiles, private credential file and log redaction, **four platforms at once** with unique ids and per-platform identities, **one source crashing / flaky while the others keep reading**, live add/disable/remove/disconnect/connect without restarting untouched sources, waiting and invalid states, jittered capped backoff, balanced / weighted / smart fairness, eviction from the busiest source, cooldown per platform identity, paid priority, the **engine answering 4 platforms with one voice at a time**, overlay events with platform and no secrets, moderator deletion, manual pick from the feed, start without sources, platform-aware reading and prompt; review regressions (no restart of sources stopped on purpose, subscription notices are not Super Chats, a message deleted mid-answer is never spoken, failed manual answers can be retried) |
| `test_connector_twitch.py` | 8 | IRC parsing and badges/Bits, guest IRC end to end (PING/PONG, USERNOTICE raid, CLEARMSG/CLEARCHAT → retract), probe of a missing channel, **EventSub**: welcome → 4 subscriptions → notifications → `session_reconnect` without re-subscribing → revocation → `auth_required`; refresh with token rotation; Device Code login and revoke; account-mode guidance; auto → guest fallback |
| `test_connector_kick.py` | 11 | Pusher chatroom lookup (manual id, Cloudflare block), handshake, messages with badges and emote cleanup, ping/pong, delete/ban, error codes; webhook: RSA signature accepted / tampered / replayed / duplicate, subscription body, Kicks mapping, unsubscribe on close, probes, bad target |
| `test_connector_tiktok.py` | 20 | fake TikTokLive: comments and flags, gift streaks (only the final event), follow/subscription, offline → waiting, not found, rate limit, missing library → unsupported, close never raises, the Euler key applied but never shown; plus one check against the real library's classes (runs only where TikTokLive is installed) |
| `test_connector_meta.py` | 18 | user token → Page token, Page token, live discovery, comments and de-duplication with `since`, backlog skip, usage-header slow-down, token/permission errors, not live → waiting, video target, personal profile, Instagram account discovery, `live_media`, 50-cap de-duplication, no token anywhere in status/exception/logs |
| `test_connector_x.py` | 11 | replies with expansions, `since_id`, root post skipped, 429 with reset, 401, plan required, broadcast → unsupported, missing bearer, no token leaks |
| `test_gui_multistream.py` | 5 | add/edit/remove sources and duplicate rejection, secrets go to the keyring and never to settings or profiles, feed model batching/cap/filters, engine messages reaching the feed with states, Streaming platforms / Live chat / Settings pages and the add dialog load **without QML warnings** |
| `test_overlay_render.py` (new test) | 1 | in headless Chrome: the "Twitch" tag appears on the viewer's message only, and a hostile label or colour is rendered as text or falls back |

Changed existing tests:
- `test_engine.py` and `test_reading.py` now approve by the source-namespaced id.
- `test_gui.py` loads 11 pages instead of 10.

## Results

```
$ python -m pytest -q
292 passed, 6 skipped in 183.35s
```

The only skips are tests that need the real Ollama/TTS (`--run-live`), a YouTube URL given
on the command line, or the optional TikTokLive library.

## Real services (manual, 2026-10-12)

Public chats only, no credentials, through the real `MultiStreamManager` at the same time:

| Source | Result |
|---|---|
| YouTube `@LofiGirl` | channel → live video resolved, connected, messages read |
| Twitch `xqc` (guest IRC) | connected, messages with ids, user ids and badges |
| Kick `absi` (public chat) | 55 messages in 45 s, 10 from moderators and 13 from subscribers |

Not exercised against real services, because no credentials or apps were available:
Twitch EventSub with an account, Kick webhooks, TikTok, Facebook, Instagram and X (see
`20-multistream-release.md`).
