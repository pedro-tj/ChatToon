"""Recognise what the streamer pasted: platform, canonical target and a duplicate key.

Pure parsing, no network: a pasted link never makes ChatToon contact an arbitrary host
(no SSRF). Connectors only talk to the fixed API hosts of their own platform; the text
typed here only becomes a channel name or an id inside those requests.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import parse_qs, urlparse

from ..youtube_chat import extract_video_id

_HANDLE_YT = re.compile(r"^@[A-Za-z0-9._-]{3,30}$")
_CHANNEL_YT = re.compile(r"^UC[A-Za-z0-9_-]{22}$")
_TWITCH = re.compile(r"^[A-Za-z0-9_]{3,25}$")
_KICK = re.compile(r"^[A-Za-z0-9_-]{3,25}$")
_TIKTOK = re.compile(r"^[A-Za-z0-9_.]{2,24}$")
_INSTAGRAM = re.compile(r"^[A-Za-z0-9_.]{1,30}$")
_FACEBOOK = re.compile(r"^[A-Za-z0-9.\-]{2,80}$")
_NUMERIC = re.compile(r"^\d{5,25}$")
_X_USER = re.compile(r"^[A-Za-z0-9_]{1,15}$")

_TWITCH_RESERVED = {"directory", "videos", "p", "settings", "downloads", "jobs", "turbo", "search", "subscriptions",
                    "inventory", "wallet", "drops", "friends", "messages", "store", "prime", "login", "signup"}
_KICK_RESERVED = {"categories", "following", "browse", "search", "dashboard", "settings", "terms-of-service",
                  "privacy-policy", "community-guidelines", "video", "clips", "login", "signup"}
_FB_RESERVED = {"watch", "gaming", "groups", "events", "pages", "profile.php", "login", "marketplace", "reel",
                "share", "photo", "story.php", "permalink.php"}
_IG_RESERVED = {"p", "reel", "reels", "explore", "accounts", "stories", "direct", "tv"}

# hosts accepted per platform (anything else is "not recognised")
_HOSTS = {
    "youtube": {"youtube.com", "youtu.be", "music.youtube.com", "studio.youtube.com", "gaming.youtube.com"},
    "twitch": {"twitch.tv", "dashboard.twitch.tv"},
    "kick": {"kick.com"},
    "tiktok": {"tiktok.com"},
    "facebook": {"facebook.com", "fb.com", "fb.watch"},
    "instagram": {"instagram.com"},
    "x": {"x.com", "twitter.com"},
}


class UrlError(ValueError):
    """``code``: empty | unknown | invalid | short-link | ambiguous | unsupported."""

    def __init__(self, code: str, message: str = ""):
        super().__init__(message or code)
        self.code = code


@dataclass(frozen=True)
class Detected:
    platform: str
    target: str  # canonical value stored in the source (URL or name)
    display: str  # what the interface shows ("@canal", "canal_linux", "video AbCd…")
    key: str  # duplicate detection: same key = same chat
    kind: str = "channel"  # channel | video | post


def _host(parsed) -> str:
    host = (parsed.hostname or "").lower()
    for prefix in ("www.", "m.", "mobile.", "web.", "vm.", "vt."):
        host = host.removeprefix(prefix)
    return host


def platform_of_host(host: str) -> str:
    for platform, hosts in _HOSTS.items():
        if host in hosts:
            return platform
    return ""


def _parts(parsed) -> list[str]:
    return [p for p in parsed.path.split("/") if p]


def detect(text: str, platform: str = "") -> Detected:
    """Parse ``text`` (URL or bare name). ``platform`` is the streamer's choice in the form;
    without it a bare name is ambiguous and only URLs are recognised."""
    raw = (text or "").strip()
    if not raw:
        raise UrlError("empty")
    if len(raw) > 500 or any(c.isspace() for c in raw):
        raise UrlError("invalid")
    scheme = re.match(r"^([a-z][a-z0-9+.-]*):", raw, re.I)
    if scheme and scheme.group(1).lower() not in ("http", "https", "post", "video", "broadcast"):
        raise UrlError("invalid")  # javascript:, file:, ftp:… never reach a parser
    looks_like_url = "/" in raw or (not platform and re.search(r"\.(com|tv|be|watch)\b", raw, re.I))
    if looks_like_url:
        candidate = raw if re.match(r"^[a-z]+://", raw, re.I) else "https://" + raw
        parsed = urlparse(candidate)
        if parsed.scheme.lower() not in ("http", "https"):
            raise UrlError("invalid")
        found = platform_of_host(_host(parsed))
        if not found:
            raise UrlError("unknown")
        if platform and platform != found:
            raise UrlError("unknown", f"this is a {found} link")
        return _PARSERS[found](parsed, raw)
    if not platform:
        if _CHANNEL_YT.match(raw) or re.fullmatch(r"[A-Za-z0-9_-]{11}", raw) and re.search(r"\d", raw):
            return _youtube_bare(raw)
        raise UrlError("ambiguous")
    return _BARE[platform](raw)


# -- per platform --------------------------------------------------------------

def _youtube(parsed, raw: str) -> Detected:
    parts = _parts(parsed)
    if parts and (parts[0].startswith("@") or parts[0] in ("channel", "c", "user")):
        handle = parts[0] if parts[0].startswith("@") else (parts[1] if len(parts) > 1 else "")
        return _youtube_channel(handle if parts[0].startswith("@") else f"{parts[0]}/{handle}")
    try:
        vid = extract_video_id(raw)
    except ValueError as e:
        raise UrlError("invalid", str(e)) from None
    return Detected("youtube", f"https://www.youtube.com/watch?v={vid}", f"video {vid}", f"youtube:{vid}", "video")


def _youtube_channel(handle: str) -> Detected:
    if handle.startswith("@"):
        if not _HANDLE_YT.match(handle):
            raise UrlError("invalid")
        return Detected("youtube", f"https://www.youtube.com/{handle}/live", handle, f"youtube:{handle.lower()}")
    kind, _, name = handle.partition("/")
    if kind == "channel" and _CHANNEL_YT.match(name):
        return Detected("youtube", f"https://www.youtube.com/channel/{name}/live", name, f"youtube:{name}")
    if kind in ("c", "user") and re.fullmatch(r"[A-Za-z0-9._-]{1,60}", name):
        return Detected("youtube", f"https://www.youtube.com/{kind}/{name}/live", name, f"youtube:{kind}/{name.lower()}")
    raise UrlError("invalid")


def _youtube_bare(raw: str) -> Detected:
    if raw.startswith("@"):
        return _youtube_channel(raw)
    if _CHANNEL_YT.match(raw):
        return _youtube_channel(f"channel/{raw}")
    try:
        vid = extract_video_id(raw)
    except ValueError:
        raise UrlError("invalid") from None
    return Detected("youtube", f"https://www.youtube.com/watch?v={vid}", f"video {vid}", f"youtube:{vid}", "video")


def _twitch(parsed, raw: str) -> Detected:
    parts = _parts(parsed)
    if parts[:1] == ["popout"] and len(parts) >= 2:
        parts = parts[1:]
    if _host(parsed) == "dashboard.twitch.tv" and len(parts) >= 2 and parts[0] == "u":
        parts = parts[1:]
    if not parts or parts[0].lower() in _TWITCH_RESERVED:
        raise UrlError("invalid")
    return _twitch_bare(parts[0])


def _twitch_bare(raw: str) -> Detected:
    login = raw.lstrip("@").lower()
    if not _TWITCH.match(login):
        raise UrlError("invalid")
    return Detected("twitch", login, login, f"twitch:{login}")


def _kick(parsed, raw: str) -> Detected:
    parts = _parts(parsed)
    if parts[:1] == ["popout"] and len(parts) >= 2:
        parts = parts[1:]
    if not parts or parts[0].lower() in _KICK_RESERVED:
        raise UrlError("invalid")
    return _kick_bare(parts[0])


def _kick_bare(raw: str) -> Detected:
    slug = raw.lstrip("@").lower()
    if not _KICK.match(slug):
        raise UrlError("invalid")
    return Detected("kick", slug, slug, f"kick:{slug}")


def _tiktok(parsed, raw: str) -> Detected:
    host = (parsed.hostname or "").lower()
    if host.startswith(("vm.", "vt.")) or _parts(parsed)[:1] == ["t"]:
        raise UrlError("short-link")
    parts = _parts(parsed)
    if not parts or not parts[0].startswith("@"):
        raise UrlError("invalid")
    return _tiktok_bare(parts[0])


def _tiktok_bare(raw: str) -> Detected:
    user = raw.lstrip("@")
    if not _TIKTOK.match(user) or user.startswith(".") or user.endswith("."):
        raise UrlError("invalid")
    return Detected("tiktok", f"@{user.lower()}", f"@{user}", f"tiktok:{user.lower()}")


def _facebook(parsed, raw: str) -> Detected:
    if _host(parsed) == "fb.watch":
        raise UrlError("short-link")
    parts = _parts(parsed)
    query = parse_qs(parsed.query)
    if parts[:1] == ["watch"] and query.get("v"):
        return _facebook_video(query["v"][0])
    if "videos" in parts:
        i = parts.index("videos")
        if i + 1 < len(parts):
            return _facebook_video(parts[i + 1])
    if parts[:1] == ["profile.php"] and query.get("id"):
        return _facebook_bare(query["id"][0])
    if not parts or parts[0].lower() in _FB_RESERVED:
        raise UrlError("invalid")
    return _facebook_bare(parts[0])


def _facebook_video(video_id: str) -> Detected:
    if not _NUMERIC.match(video_id):
        raise UrlError("invalid")
    return Detected("facebook", f"video:{video_id}", f"video {video_id}", f"facebook:video:{video_id}", "video")


def _facebook_bare(raw: str) -> Detected:
    if raw.startswith("video:"):
        return _facebook_video(raw.removeprefix("video:"))
    page = raw.lstrip("@")
    if not _FACEBOOK.match(page):
        raise UrlError("invalid")
    return Detected("facebook", page, page, f"facebook:{page.lower()}")


def _instagram(parsed, raw: str) -> Detected:
    parts = _parts(parsed)
    if not parts or parts[0].lower() in _IG_RESERVED:
        raise UrlError("invalid")
    return _instagram_bare(parts[0])


def _instagram_bare(raw: str) -> Detected:
    user = raw.lstrip("@").lower()
    if not _INSTAGRAM.match(user):
        raise UrlError("invalid")
    return Detected("instagram", f"@{user}", f"@{user}", f"instagram:{user}")


def _x(parsed, raw: str) -> Detected:
    parts = _parts(parsed)
    if parts[:2] == ["i", "spaces"]:
        raise UrlError("unsupported", "X Spaces are audio rooms without a readable chat API")
    if parts[:2] == ["i", "broadcasts"] and len(parts) >= 3:
        if not re.fullmatch(r"[A-Za-z0-9]{6,30}", parts[2]):
            raise UrlError("invalid")
        return Detected("x", f"broadcast:{parts[2]}", f"broadcast {parts[2]}", f"x:broadcast:{parts[2]}", "video")
    if len(parts) >= 3 and parts[1] == "status" and _NUMERIC.match(parts[2]):
        return Detected("x", f"post:{parts[2]}", f"@{parts[0]} · {parts[2]}", f"x:post:{parts[2]}", "post")
    raise UrlError("invalid")


def _x_bare(raw: str) -> Detected:
    if _NUMERIC.match(raw):
        return Detected("x", f"post:{raw}", raw, f"x:post:{raw}", "post")
    if raw.startswith(("post:", "broadcast:")):
        kind, _, value = raw.partition(":")
        if kind == "post" and _NUMERIC.match(value):
            return Detected("x", raw, value, f"x:{raw}", "post")
        if kind == "broadcast" and re.fullmatch(r"[A-Za-z0-9]{6,30}", value):
            return Detected("x", raw, value, f"x:{raw}", "video")
    raise UrlError("invalid")


_PARSERS = {"youtube": _youtube, "twitch": _twitch, "kick": _kick, "tiktok": _tiktok, "facebook": _facebook,
            "instagram": _instagram, "x": _x}
_BARE = {"youtube": _youtube_bare, "twitch": _twitch_bare, "kick": _kick_bare, "tiktok": _tiktok_bare,
         "facebook": _facebook_bare, "instagram": _instagram_bare, "x": _x_bare}


def source_key(platform: str, target: str) -> str:
    """Duplicate key of a stored source ("" if the target no longer parses)."""
    try:
        return detect(target, platform).key
    except UrlError:
        return ""
