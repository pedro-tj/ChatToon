"""Multistream: read the chat of several platforms at the same time.

``PLATFORMS`` is the honest capability sheet shown in the interface. Levels:

* functional — official or long-standing public method, tested with fakes and real data;
* limited — works only with conditions the streamer must meet (paid API, approved app,
  professional account, public webhook);
* experimental — unofficial method; may break without notice;
* unavailable — the platform offers no way to read it (the source stays disabled).

Details and evidence: docs/PLATFORMS.md.
"""

from __future__ import annotations

PLATFORMS: dict[str, dict] = {
    "youtube": {
        "label": "YouTube", "color": "#ff0033", "glyph": "YT", "support": "functional", "auth": "none",
        "accepts": "youtube.com/watch?v=…, /live/…, youtu.be/…, @channel",
        "events": ["message", "paid", "membership"],
    },
    "twitch": {
        "label": "Twitch", "color": "#9146ff", "glyph": "TW", "support": "functional", "auth": "optional",
        "accepts": "twitch.tv/channel, channel",
        "events": ["message", "paid", "subscription", "raid"],
    },
    "kick": {
        "label": "Kick", "color": "#53fc18", "glyph": "K", "support": "limited", "auth": "optional",
        "accepts": "kick.com/channel, channel",
        "events": ["message", "subscription", "gift"],
    },
    "tiktok": {
        "label": "TikTok", "color": "#fe2c55", "glyph": "TT", "support": "experimental", "auth": "none",
        "accepts": "tiktok.com/@user/live, @user",
        "events": ["message", "gift", "follow", "subscription"],
        "requires": "TikTokLive",
    },
    "facebook": {
        "label": "Facebook", "color": "#1877f2", "glyph": "f", "support": "limited", "auth": "required",
        "accepts": "facebook.com/page, facebook.com/…/videos/ID",
        "events": ["message"],
    },
    "instagram": {
        "label": "Instagram", "color": "#e1306c", "glyph": "IG", "support": "limited", "auth": "required",
        "accepts": "instagram.com/user, @user",
        "events": ["message"],
    },
    "x": {
        "label": "X", "color": "#71767b", "glyph": "X", "support": "limited", "auth": "required",
        "accepts": "x.com/user/status/ID",
        "events": ["message"],
    },
}


def platform_label(platform: str) -> str:
    info = PLATFORMS.get(platform)
    return info["label"] if info else platform.capitalize()
