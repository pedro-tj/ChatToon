"""Chat messages, validation and the selection engine that decides what to answer.

Busy chats produce far more messages than an avatar can answer. The selector keeps a
bounded queue, drops expired/abusive messages, enforces a per-viewer cooldown and picks
the next message according to the configured mode, with an age bonus so nobody waits
forever (no starvation).

Messages may come from several platforms and sources at once (multistream). Every
message carries its platform and source id: identities ("who is this viewer?") and
message ids are namespaced by source, so "ana" on Twitch and "ana" on YouTube are two
different people, and two platforms can never collide on a message id. When several
sources have messages waiting, the selector shares the avatar's attention between them
(stride scheduling) instead of always answering the busiest chat.
"""

from __future__ import annotations

import random
import re
import time
import unicodedata
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field

SELECTION_MODES = ("smart", "balanced", "weighted", "all", "mentions", "questions", "moderators", "members",
                   "random", "manual")
# modes that share attention between sources before looking at the messages themselves
FAIR_MODES = ("balanced", "weighted")
EVENT_TYPES = ("message", "paid", "subscription", "gift", "follow", "raid", "system")

_QUESTION_WORDS = re.compile(
    r"^(qual|quais|quem|quando|onde|como|por ?que|porque|o que|que|quanto|quantos|será|pode|tem|vc|você|"
    r"what|who|when|where|why|how|which|can|do|does|is|are)\b",
    re.IGNORECASE,
)
_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f​-‏‪-‮⁦-⁩]")


@dataclass
class ChatMessage:
    id: str  # id given by the platform (unique inside one source)
    author: str
    text: str
    timestamp: float = field(default_factory=time.time)  # wall clock (seconds)
    author_id: str = ""
    platform: str = "youtube"  # youtube | twitch | kick | tiktok | facebook | instagram | x | demo | manual
    is_moderator: bool = False
    is_member: bool = False  # channel member / subscriber
    is_owner: bool = False
    is_verified: bool = False
    superchat: str = ""  # label of a paid message ("R$ 10,00", "100 bits", "Rosa ×5")
    received: float = field(default_factory=time.monotonic)
    source_id: str = ""  # configured source the message came from ("" = demo/manual/legacy)
    channel: str = ""  # channel or live being read (display only)
    event_type: str = "message"  # see EVENT_TYPES
    paid_kind: str = ""  # superchat | supersticker | bits | gift | kicks | stars | membership | ...

    @property
    def uid(self) -> str:
        """Globally unique id: the platform id namespaced by its source."""
        return f"{self.source_id}:{self.id}" if self.source_id else self.id

    @property
    def source_key(self) -> str:
        return self.source_id or self.platform

    @property
    def key(self) -> str:
        """Identity of the viewer inside one source (cooldowns, repetition, memory)."""
        return f"{self.platform}:{self.source_id}:{self.author_id or self.author.casefold()}"

    @property
    def is_paid(self) -> bool:
        """Money or gifts (Super Chat, Bits, Kicks, TikTok gifts) — not subscription/raid notices."""
        return bool(self.superchat) and self.event_type not in ("subscription", "raid", "follow", "system")

    @property
    def is_superchat(self) -> bool:
        return self.is_paid and self.paid_kind in ("", "superchat", "supersticker")

    @property
    def is_question(self) -> bool:
        t = self.text.strip()
        return "?" in t or bool(_QUESTION_WORDS.match(t))

    def to_dict(self) -> dict:
        return {
            "id": self.uid, "message_id": self.id, "author": self.author, "text": self.text,
            "timestamp": self.timestamp, "platform": self.platform, "source_id": self.source_id,
            "channel": self.channel, "event": self.event_type, "moderator": self.is_moderator,
            "member": self.is_member, "owner": self.is_owner, "verified": self.is_verified,
            "superchat": self.superchat, "paid_kind": self.paid_kind, "question": self.is_question,
        }


def clean_text(text: str, limit: int = 300) -> str:
    """Remove control/bidi characters, collapse spaces and cap the length."""
    text = _CONTROL.sub("", unicodedata.normalize("NFC", text or ""))
    text = " ".join(text.split())
    if len(text) > limit:
        text = text[:limit].rsplit(" ", 1)[0] + "…"
    return text


def _fold(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def mentions(text: str, names: tuple[str, ...]) -> bool:
    folded = _fold(text)
    for name in names:
        n = re.escape(_fold(name))
        if re.search(rf"(?<![\w]){n}(?![\w])", folded):
            return True
    return False


def has_words(text: str) -> bool:
    return any(c.isalnum() for c in text)


@dataclass
class SelectorConfig:
    mode: str = "smart"
    user_cooldown: float = 60
    max_queue: int = 40
    ttl: float = 120
    max_chars: int = 300
    ignore_commands: bool = True
    blocked_words: tuple[str, ...] = ()
    superchat_priority: bool = True
    names: tuple[str, ...] = ()  # avatar names for mention detection
    weights: dict[str, float] = field(default_factory=dict)  # source id -> share of attention (weighted mode)
    fairness: bool = True  # smart & co. also avoid answering only the busiest source
    include_events: bool = False  # gifts, follows, subscriptions without text may be answered
    priority_authors: tuple[str, ...] = ()  # "platform:name" (or just "name") of favourite viewers


class MessageSelector:
    def __init__(
        self,
        config: SelectorConfig,
        clock: Callable[[], float] = time.monotonic,
        rng: random.Random | None = None,
    ):
        self.config = config
        self.clock = clock
        self.rng = rng or random.Random()
        self._queue: list[ChatMessage] = []
        self._answered_at: dict[str, float] = {}
        self._recent_text: dict[str, tuple[str, float]] = {}
        self._pass: dict[str, float] = {}  # stride scheduling: virtual time of each source
        self._vt = 0.0  # global virtual time (start of the latest turn)
        self._recent_sources: deque[str] = deque(maxlen=12)
        self.dropped = 0
        # told about queued messages that leave without an answer (expired, pushed out)
        self.on_discard: Callable[[ChatMessage, str], None] = lambda msg, reason: None

    # -- intake -----------------------------------------------------------

    def offer(self, msg: ChatMessage) -> str:
        """Validate and enqueue. Returns "" when accepted, else the reason it was dropped."""
        cfg = self.config
        msg.text = clean_text(msg.text, cfg.max_chars)
        msg.author = clean_text(msg.author, 60) or "?"
        msg.received = self.clock()
        reason = self._reject_reason(msg)
        if reason:
            self.dropped += 1
            return reason
        self._recent_text[msg.key] = (_fold(msg.text), msg.received)
        if len(self._recent_text) > 5000:  # long lives: forget the oldest viewers
            for k in list(self._recent_text)[:1000]:
                del self._recent_text[k]
        self._queue.append(msg)
        self._expire()
        if len(self._queue) > cfg.max_queue:
            worst = self._eviction_candidate()
            self._queue.remove(worst)
            self.dropped += 1
            if worst is msg:
                return "queue full"
            self.on_discard(worst, "queue full")
        return ""

    def _reject_reason(self, msg: ChatMessage) -> str:
        cfg = self.config
        text = msg.text
        event = msg.event_type not in ("message", "paid")
        if event and not cfg.include_events:
            return "event"
        if not event and (not text or not has_words(text)):
            return "empty"
        if cfg.ignore_commands and text.startswith("!"):
            return "command"
        folded = _fold(text)
        if any(w and _fold(w) in folded for w in cfg.blocked_words):
            return "blocked word"
        uid = msg.uid
        if any(m.uid == uid for m in self._queue):
            return "duplicate"
        last = self._recent_text.get(msg.key)
        if last and last[0] == folded and msg.received - last[1] < 30:
            return "repeated"
        if cfg.mode == "mentions" and not mentions(text, cfg.names) and not msg.is_paid:
            return "no mention"
        return ""

    def _eviction_candidate(self) -> ChatMessage:
        """The message dropped when the queue is full: the worst one of the busiest source,
        so a flood on one platform never pushes the quieter platforms out of the queue."""
        counts: dict[str, int] = {}
        for m in self._queue:
            counts[m.source_key] = counts.get(m.source_key, 0) + 1
        busiest = max(counts.values())
        pool = [m for m in self._queue if counts[m.source_key] == busiest]
        return min(pool, key=self._score)

    # -- selection --------------------------------------------------------

    def _expire(self) -> None:
        now = self.clock()
        ttl = self.config.ttl
        expired = [m for m in self._queue if now - m.received > ttl]
        if expired:
            self._queue = [m for m in self._queue if now - m.received <= ttl]
            self.dropped += len(expired)
            for m in expired:
                self.on_discard(m, "expired")

    def _eligible(self, msg: ChatMessage) -> bool:
        last = self._answered_at.get(msg.key)
        if last is None:
            return True
        if msg.is_paid and self.config.superchat_priority:
            return True  # paid messages skip the cooldown (they are rate limited by money)
        return self.clock() - last >= self.config.user_cooldown

    def _favourite(self, msg: ChatMessage) -> bool:
        wanted = self.config.priority_authors
        if not wanted:
            return False
        name = msg.author.casefold().lstrip("@")
        return name in wanted or f"{msg.platform}:{name}" in wanted

    def _fairness_bonus(self, msg: ChatMessage, active: int) -> float:
        """Sources that got fewer of the latest answers than their share gain priority."""
        if not self.config.fairness or active < 2 or not self._recent_sources:
            return 0.0
        share = self._recent_sources.count(msg.source_key) / len(self._recent_sources)
        return max(-2.5, min(2.5, (1 / active - share) * 5))

    def _score(self, msg: ChatMessage, active: int = 1) -> float:
        cfg = self.config
        age = self.clock() - msg.received
        score = 1.0 + min(age / max(cfg.ttl, 1), 1.0) * 2.0  # waiting raises priority (no starvation)
        if mentions(msg.text, cfg.names):
            score += 3.0
        if msg.is_question:
            score += 2.0 if cfg.mode in ("smart", "questions", "balanced", "weighted") else 0.5
        if msg.is_moderator or msg.is_owner:
            score += 4.0 if cfg.mode == "moderators" else 1.5
        if msg.is_member:
            score += 4.0 if cfg.mode == "members" else 1.0
        if msg.is_paid and cfg.superchat_priority:
            score += 8.0  # paid messages outrank any mention/question combination
        if self._favourite(msg):
            score += 3.0
        if len(msg.text) < 4:
            score -= 1.5
        if cfg.mode == "questions" and msg.is_question:
            score += 4.0
        return score + self._fairness_bonus(msg, active)

    def next(self) -> ChatMessage | None:
        """Pop the next message to answer (None in manual mode or when nothing is eligible)."""
        self._expire()
        if self.config.mode == "manual":
            return None
        candidates = [m for m in self._queue if self._eligible(m)]
        if not candidates:
            return None
        mode = self.config.mode
        active = len({m.source_key for m in candidates})
        if mode == "all":
            chosen = min(candidates, key=lambda m: m.received)
        elif mode == "random":
            chosen = self.rng.choice(candidates)
        elif mode in FAIR_MODES:
            chosen = self._fair_pick(candidates)
        else:
            # small jitter keeps equal scores from always favouring the same position
            chosen = max(candidates, key=lambda m: self._score(m, active) + self.rng.random() * 0.3)
        return self._take(chosen)

    def _weight(self, source: str) -> float:
        if self.config.mode != "weighted":
            return 1.0
        return max(0.1, float(self.config.weights.get(source, 1.0)))

    def _fair_pick(self, candidates: list[ChatMessage]) -> ChatMessage:
        """Stride scheduling: each source advances its virtual time by 1/weight per answer;
        the source furthest behind goes next. Paid messages still jump the line."""
        best = lambda pool: max(pool, key=lambda m: self._score(m) + self.rng.random() * 0.3)  # noqa: E731
        if self.config.superchat_priority:
            paid = [m for m in candidates if m.is_paid]
            if paid:
                return best(paid)
        sources = {m.source_key for m in candidates}
        oldest = {s: min(m.received for m in candidates if m.source_key == s) for s in sources}
        source = min(sources, key=lambda s: (self._effective_pass(s), oldest[s]))
        return best([m for m in candidates if m.source_key == source])

    def _effective_pass(self, source: str) -> float:
        # a source that was quiet for a while rejoins at the current virtual time: it gets
        # its turn right away, but no burst of "saved up" turns
        return max(self._pass.get(source, 0.0), self._vt)

    def take(self, message_id: str) -> ChatMessage | None:
        """Manual approval: pop a specific message (by uid)."""
        for m in self._queue:
            if m.uid == message_id:
                return self._take(m)
        return None

    def _take(self, msg: ChatMessage) -> ChatMessage:
        self._queue.remove(msg)
        self.mark_answered(msg)
        return msg

    def mark_answered(self, msg: ChatMessage) -> None:
        """Record an answer (also used for messages answered by hand from the feed)."""
        self._answered_at[msg.key] = self.clock()
        if len(self._answered_at) > 5000:
            for k in list(self._answered_at)[:1000]:
                del self._answered_at[k]
        source = msg.source_key
        start = self._effective_pass(source)
        self._vt = start
        self._pass[source] = start + 1 / self._weight(source)
        self._recent_sources.append(source)

    def remove(self, message_id: str) -> bool:
        before = len(self._queue)
        self._queue = [m for m in self._queue if m.uid != message_id]
        return len(self._queue) != before

    def clear(self) -> None:
        self._queue.clear()

    def forget_source(self, source: str) -> None:
        """A source was removed: drop its queued messages and scheduling state."""
        self._queue = [m for m in self._queue if m.source_key != source]
        self._pass.pop(source, None)

    def pending(self) -> list[ChatMessage]:
        self._expire()
        active = len({m.source_key for m in self._queue})
        return sorted(self._queue, key=lambda m: self._score(m, active), reverse=True)

    def counts(self) -> dict[str, int]:
        """Queued messages per source."""
        out: dict[str, int] = {}
        for m in self._queue:
            out[m.source_key] = out.get(m.source_key, 0) + 1
        return out

    def __len__(self) -> int:
        return len(self._queue)
