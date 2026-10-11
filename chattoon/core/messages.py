"""Chat messages, validation and the selection engine that decides what to answer.

Busy chats produce far more messages than an avatar can answer. The selector keeps a
bounded queue, drops expired/abusive messages, enforces a per-viewer cooldown and picks
the next message according to the configured mode, with an age bonus so nobody waits
forever (no starvation).
"""

from __future__ import annotations

import random
import re
import time
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass, field

SELECTION_MODES = ("all", "smart", "mentions", "questions", "moderators", "members", "random", "manual")

_QUESTION_WORDS = re.compile(
    r"^(qual|quais|quem|quando|onde|como|por ?que|porque|o que|que|quanto|quantos|será|pode|tem|vc|você|"
    r"what|who|when|where|why|how|which|can|do|does|is|are)\b",
    re.IGNORECASE,
)
_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f​-‏‪-‮⁦-⁩]")


@dataclass
class ChatMessage:
    id: str
    author: str
    text: str
    timestamp: float = field(default_factory=time.time)  # wall clock (seconds)
    author_id: str = ""
    platform: str = "youtube"  # youtube | demo | manual
    is_moderator: bool = False
    is_member: bool = False
    is_owner: bool = False
    is_verified: bool = False
    superchat: str = ""  # amount text ("R$ 10,00") for paid messages
    received: float = field(default_factory=time.monotonic)

    @property
    def key(self) -> str:
        return self.author_id or self.author.casefold()

    @property
    def is_question(self) -> bool:
        t = self.text.strip()
        return "?" in t or bool(_QUESTION_WORDS.match(t))

    def to_dict(self) -> dict:
        return {
            "id": self.id, "author": self.author, "text": self.text, "timestamp": self.timestamp,
            "platform": self.platform, "moderator": self.is_moderator, "member": self.is_member,
            "owner": self.is_owner, "superchat": self.superchat, "question": self.is_question,
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
        self.dropped = 0

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
        self._queue.append(msg)
        self._expire()
        if len(self._queue) > cfg.max_queue:
            worst = min(self._queue, key=self._score)
            self._queue.remove(worst)
            self.dropped += 1
            if worst is msg:
                return "queue full"
        return ""

    def _reject_reason(self, msg: ChatMessage) -> str:
        cfg = self.config
        text = msg.text
        if not text or not has_words(text):
            return "empty"
        if cfg.ignore_commands and text.startswith("!"):
            return "command"
        folded = _fold(text)
        if any(w and _fold(w) in folded for w in cfg.blocked_words):
            return "blocked word"
        if any(m.id == msg.id for m in self._queue):
            return "duplicate"
        last = self._recent_text.get(msg.key)
        if last and last[0] == folded and msg.received - last[1] < 30:
            return "repeated"
        if cfg.mode == "mentions" and not mentions(text, cfg.names) and not msg.superchat:
            return "no mention"
        return ""

    # -- selection --------------------------------------------------------

    def _expire(self) -> None:
        now = self.clock()
        before = len(self._queue)
        self._queue = [m for m in self._queue if now - m.received <= self.config.ttl]
        self.dropped += before - len(self._queue)

    def _eligible(self, msg: ChatMessage) -> bool:
        last = self._answered_at.get(msg.key)
        if last is None:
            return True
        if msg.superchat and self.config.superchat_priority:
            return True  # paid messages skip the cooldown (they are rate limited by money)
        return self.clock() - last >= self.config.user_cooldown

    def _score(self, msg: ChatMessage) -> float:
        cfg = self.config
        age = self.clock() - msg.received
        score = 1.0 + min(age / max(cfg.ttl, 1), 1.0) * 2.0  # waiting raises priority (no starvation)
        if mentions(msg.text, cfg.names):
            score += 3.0
        if msg.is_question:
            score += 2.0 if cfg.mode in ("smart", "questions") else 0.5
        if msg.is_moderator or msg.is_owner:
            score += 4.0 if cfg.mode == "moderators" else 1.5
        if msg.is_member:
            score += 4.0 if cfg.mode == "members" else 1.0
        if msg.superchat and cfg.superchat_priority:
            score += 8.0  # paid messages outrank any mention/question combination
        if len(msg.text) < 4:
            score -= 1.5
        if cfg.mode == "questions" and msg.is_question:
            score += 4.0
        return score

    def next(self) -> ChatMessage | None:
        """Pop the next message to answer (None in manual mode or when nothing is eligible)."""
        self._expire()
        if self.config.mode == "manual":
            return None
        candidates = [m for m in self._queue if self._eligible(m)]
        if not candidates:
            return None
        mode = self.config.mode
        if mode == "all":
            chosen = min(candidates, key=lambda m: m.received)
        elif mode == "random":
            chosen = self.rng.choice(candidates)
        else:
            # small jitter keeps equal scores from always favouring the same position
            chosen = max(candidates, key=lambda m: self._score(m) + self.rng.random() * 0.3)
        return self._take(chosen)

    def take(self, message_id: str) -> ChatMessage | None:
        """Manual approval: pop a specific message."""
        for m in self._queue:
            if m.id == message_id:
                return self._take(m)
        return None

    def _take(self, msg: ChatMessage) -> ChatMessage:
        self._queue.remove(msg)
        self._answered_at[msg.key] = self.clock()
        return msg

    def remove(self, message_id: str) -> bool:
        before = len(self._queue)
        self._queue = [m for m in self._queue if m.id != message_id]
        return len(self._queue) != before

    def clear(self) -> None:
        self._queue.clear()

    def pending(self) -> list[ChatMessage]:
        self._expire()
        return sorted(self._queue, key=self._score, reverse=True)

    def __len__(self) -> int:
        return len(self._queue)
