# 26 — Stream context: platform data and AI suggestions

"Stream context" can now be filled from the streamer's own sources, with every
suggestion shown for approval. Code: `chattoon/core/assistant.py`, `metadata()` in each
connector, `StreamPage.qml`.

## What each platform provides

Each connector implements `metadata()` only through what is sanctioned and already used
to read its chat. No scraping, no new logins:

| Platform | Method | Provides | Does not provide |
|---|---|---|---|
| YouTube | official **oEmbed** endpoint (no key, no login) | live title, channel name, channel URL | description, tags (need the YouTube Data API key, which ChatToon does not use) |
| Twitch | official **Helix** API with the connected account | title, category (game), tags, live or not, channel name | channel description |
| Kick | kick.com's channel endpoint (the same unofficial one the chat reader uses) | title, category, tags, bio, live or not | — |
| Facebook | official **Graph API** with the token already given for comments | Page name, about, category, link, current live title/description | — |
| Instagram, TikTok, X | — | — (shown as "the platform does not provide it") | everything |

Twitch without a login answers "needs the platform login". Errors become stable codes
(offline, auth-required, not-found, network, rate-limited, invalid, unavailable). The
interface shows them per source with the time the data was read.

Caching: results are reused for 10 minutes. "Read from sources" refreshes at most once
every 30 seconds per source. A source whose platform or target changed is read again.

## Suggestions per field

| Field | How | Never |
|---|---|---|
| Channel name | the channel name from the data | — |
| Host | the platform **account name**, offered for confirmation | presented as the person's real name |
| Today's topic | the live title, cleaned (emojis, hashtags, "AO VIVO \|") | — |
| Links and projects | channel URLs from the data + the sources' URLs, merged with yours | — |
| Guests | **not suggested**: no platform says who the guests are | guessed |
| Description | the local model, 2–3 sentences from the data and what you wrote | invented dates, prizes, schedules, guests |
| Channel catchphrases | the model, 3 new ideas | presented as phrases the community already uses |
| Welcome topics | the model, 4–8 topics | — |
| Forbidden topics | the model, respectful moderation suggestions | removing or overriding yours |
| Calls to action | the model, 4 short lines suited to your platforms | switching calls to action on |

List fields (catchphrases, topics, calls to action, links) are **merged**: your items
stay first and untouched, new ones are appended without duplicates. The dialog says so.

Platform text is untrusted: it travels between `<<<` and `>>>` (delimiters inside it are
neutralised), and the model is told never to follow instructions found there.

## The dialog

The ✦ button next to each field (and "Suggest" in Calls to action) opens "AI assistant —
field": which sources to use (when there are several), information found (with read time
and source), sources without data, **conflicts** ("Your sources disagree — choose which
ones to use"), the current value, the suggestion in an editable box ("written by AI —
check it" / "taken from your sources"), and Cancel · Edit · Regenerate · Apply suggestion.
Nothing changes until Apply. Errors are explicit: no data to suggest from, no model
chosen, the AI failed (try again), no platform says who the guests are.

## Tests

`tests/test_assistant.py`: cache and refresh limit; error codes; conflicts reported, not
resolved; channel/host/topic/links from data; guests never guessed; no data → no
suggestion; AI fields merged with the streamer's values; platform text cannot close the
data block; AI failure reported; YouTube oEmbed against a local fake server; Twitch
without login; Kick channel endpoint. Visual check: the dialog was rendered offscreen in
both themes and inspected.

Real-world check: one oEmbed request for a real configured YouTube live returned its
channel name, title and channel URL (`ok`, `found`). Not verified against the real
platforms: Twitch Helix, the Graph API and the Kick endpoint were exercised with fakes
only (no logins were available; tests make no network calls).
