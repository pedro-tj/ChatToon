"""Spontaneous lines: the avatar speaks up when the chat is quiet, like a co-host.

The scheduler only decides *when* and *what kind*; the engine decides whether the
avatar is free (live, idle, empty queue, nothing to approve) and plays it with the
lowest priority of all:

    emergency/interrupt > streamer commands > priority messages > chat replies > spontaneous

A viewer's message that arrives while a spontaneous line is still being prepared cancels
it; one that arrives while it is already being spoken waits for that single short line
to end (lines never overlap — the engine's speech lock guarantees it).

What is said comes from :mod:`knowledge` (verified curiosities are spoken exactly as
written), from the stream context (topic, catchphrases, calls to action) or — for
invitations and asides only — from the model, told not to state facts. Anti-repetition:
the same category is not used twice in a row and a line is not repeated until the
others were used.
"""

from __future__ import annotations

import random
import re
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime

from . import knowledge
from .config import ChannelContext, SpontaneousSettings

FREQUENCY = {"low": 1.8, "normal": 1.0, "high": 0.55}
INTENSITY = {"calm": 0.45, "normal": 0.7, "lively": 0.95}
WEIGHTS = {"invite": 3.0, "curiosity": 3.0, "context": 2.0, "humor": 2.0, "reflection": 1.0, "catchphrase": 1.0,
           "cta": 1.0}
# the face and a generic gesture (every character has these) for each kind of line
LOOK = {"invite": ("happy", "", "lookAround"), "curiosity": ("happy", "thinking", ""), "context": ("happy", "", ""),
        "humor": ("laugh", "", ""), "reflection": ("thinking", "", "curious"), "catchphrase": ("celebrate", "", ""),
        "cta": ("happy", "", "glance")}
# categories the model may write (never curiosities: facts are spoken as written)
AI_CATEGORIES = ("invite", "context", "humor", "reflection")


@dataclass
class Plan:
    category: str
    text: str = ""  # "" = ask the model
    kind: str = ""  # fact | fiction | invite | humor | reflection | channel | catchphrase | cta | ai
    emotion: str = "happy"
    lead: str = ""
    gesture: str = ""
    intensity: float = 0.7


def _minutes(value: str) -> int | None:
    m = re.fullmatch(r"\s*(\d{1,2}):(\d{2})\s*", value or "")
    if not m or int(m.group(1)) > 23 or int(m.group(2)) > 59:
        return None
    return int(m.group(1)) * 60 + int(m.group(2))


def quiet_now(cfg: SpontaneousSettings, now: datetime | None = None) -> bool:
    start, end = _minutes(cfg.quiet_start), _minutes(cfg.quiet_end)
    if start is None or end is None or start == end:
        return False
    now = now or datetime.now()
    t = now.hour * 60 + now.minute
    return start <= t < end if start < end else (t >= start or t < end)  # e.g. 23:00 → 07:00


class Scheduler:
    def __init__(self, rng: random.Random | None = None, clock=time.monotonic):
        self.rng = rng or random.Random()
        self.clock = clock
        self.last_spoken = -1e9
        self.started = clock()
        self.not_before = 0.0
        self.used: deque[str] = deque(maxlen=60)
        self.recent_categories: deque[str] = deque(maxlen=2)
        self.count = 0

    def due(self, cfg: SpontaneousSettings, idle_for: float, now: datetime | None = None) -> bool:
        """Time for a line? (The engine separately checks that the avatar is free.)"""
        if not cfg.enabled or quiet_now(cfg, now):
            return False
        scale = FREQUENCY.get(cfg.frequency, 1.0)
        return (self.clock() >= self.not_before and idle_for >= max(15, cfg.min_idle) * scale
                and self.clock() - self.last_spoken >= max(30, cfg.min_interval) * scale)

    def spoken(self, plan: Plan) -> None:
        self.last_spoken = self.clock()
        self.count += 1
        self.recent_categories.append(plan.category)
        if plan.text:
            self.used.append(plan.text)

    def postpone(self, seconds: float = 30) -> None:
        """Nothing could be said now (the model failed, a viewer came first): try again later."""
        self.not_before = self.clock() + seconds

    # -- choosing ------------------------------------------------------------------------

    def options(self, cfg: SpontaneousSettings, character_id: str, language: str, ctx: ChannelContext,
                catchphrases: list[str], curiosities: list[str], use_ai: bool) -> dict[str, list]:
        """Category -> available lines (an empty list = only the model can write it)."""
        bank = knowledge.lines(character_id, language, curiosities)
        out: dict[str, list] = {}
        allowed = set(cfg.categories) & set(knowledge.CATEGORIES)
        for category in allowed:
            if category in ("invite", "humor", "reflection", "curiosity"):
                found = [line for line in bank if line.category == category]
                if found or (use_ai and category in AI_CATEGORIES):
                    out[category] = found
            elif category == "context":
                topic = " ".join((ctx.topic or "").split())[:120]
                if use_ai and (topic or ctx.description.strip()):
                    out[category] = []  # written by the model from the stream topic
                elif topic:
                    pt = language.lower().startswith("pt")
                    out[category] = [knowledge.Line(
                        f"O assunto de hoje é {topic}! Quem tiver pergunta ou comentário sobre isso, manda no chat."
                        if pt else f"Today's topic is {topic}! Questions or comments about it? Send them in the chat.",
                        "channel", "context")]
            elif category == "catchphrase":
                phrases = [p for p in catchphrases if p.strip()]
                phrases += [p.strip() for p in re.split(r"[\n|;]+", ctx.catchphrases or "") if len(p.strip()) > 3]
                if phrases:
                    out[category] = [knowledge.Line(p, "catchphrase", "catchphrase") for p in phrases]
            elif category == "cta":
                promos = [p for p in ctx.promo_messages if p.strip()]
                if promos:
                    out[category] = [knowledge.Line(p, "cta", "cta") for p in promos]
        return out

    def plan(self, cfg: SpontaneousSettings, character_id: str, language: str, ctx: ChannelContext,
             catchphrases: list[str] | None = None, curiosities: list[str] | None = None,
             category: str = "") -> Plan | None:
        use_ai = cfg.use_ai
        options = self.options(cfg, character_id, language, ctx, catchphrases or [], curiosities or [], use_ai)
        if category:
            if category not in options:
                # a manual test of a category that is not enabled still works
                forced = SpontaneousSettings(categories=[category], use_ai=use_ai)
                options = self.options(forced, character_id, language, ctx, catchphrases or [], curiosities or [],
                                       use_ai)
            if category not in options:
                return None
            chosen = category
        else:
            pool = {c: WEIGHTS.get(c, 1.0) for c in options
                    if c not in self.recent_categories or len(options) <= len(self.recent_categories)}
            if not pool:
                return None
            r, chosen = self.rng.random() * sum(pool.values()), next(iter(pool))
            for c, w in pool.items():
                r -= w
                if r <= 0:
                    chosen = c
                    break
        lines = options[chosen]
        fresh = [line for line in lines if line.text not in self.used]
        if not fresh and lines:
            # every line of this kind was said: the one said longest ago comes back first
            last = {text: i for i, text in enumerate(self.used)}
            fresh = [min(lines, key=lambda line: last.get(line.text, -1))]
        emotion, lead, gesture = LOOK.get(chosen, ("happy", "", ""))
        intensity = INTENSITY.get(cfg.intensity, 0.7)
        if cfg.intensity == "calm":
            gesture = ""
        # the model varies invitations and asides half of the time; facts never
        if chosen in AI_CATEGORIES and use_ai and (not fresh or chosen == "context" or self.rng.random() < 0.5):
            return Plan(chosen, "", "ai", emotion, lead, gesture, intensity)
        if not fresh:
            return None
        line = self.rng.choice(fresh)
        if line.kind == "fiction":
            emotion, lead = "laugh", ""
        return Plan(chosen, line.text, line.kind, emotion, lead, gesture, intensity)

    @staticmethod
    def instruction(plan: Plan, ctx: ChannelContext, language: str, quiet_minutes: float) -> str:
        """What the model is asked to write (only for AI_CATEGORIES)."""
        pt = language.lower().startswith("pt")
        topic = (ctx.topic or ctx.description or "").strip()[:200]
        what = {
            "invite": ("convide o público a conversar com você ou a fazer uma pergunta, de um jeito divertido",
                       "invite the audience to talk to you or ask a question, in a fun way"),
            "context": (f"faça um comentário animado sobre o assunto da live ({topic}) e convide o chat a participar",
                        f"make an upbeat remark about the stream topic ({topic}) and invite the chat in"),
            "humor": ("faça uma observação engraçada sobre o chat estar quieto ou sobre você mesmo",
                      "make a funny remark about the quiet chat or about yourself"),
            "reflection": ("compartilhe um pensamento curto e engraçado, do seu jeito",
                           "share a short, funny thought of your own"),
        }[plan.category][0 if pt else 1]
        minutes = max(1, round(quiet_minutes))
        if pt:
            return (f"[Fala espontânea] Ninguém escreve no chat há uns {minutes} minuto(s). Fale por conta própria, "
                    f"em UMA ou DUAS frases curtas: {what}. Não responda a ninguém, não cite nomes de espectadores, "
                    "não invente fatos, números, notícias nem informações sobre o canal, e não diga 'você sabia'. "
                    "Responda só com o JSON de sempre.")
        return (f"[Spontaneous line] Nobody has written in the chat for about {minutes} minute(s). Speak on your own, "
                f"in ONE or TWO short sentences: {what}. Do not answer anyone, do not name viewers, do not invent facts, "
                "numbers, news or channel information, and do not say 'did you know'. Reply only with the usual JSON.")


_FACT_CLAIM = re.compile(r"\d|\b(voce sabia|sabia que|sabiam que|curiosidade|did you know|fun fact|estudos|cientistas|"
                         r"pesquisa|segundo)\b")


def acceptable(text: str) -> bool:
    """A model-written spontaneous line must not smuggle in facts (no numbers, no 'did you know')."""
    from .intent import fold

    return bool(text) and len(text) >= 12 and not _FACT_CLAIM.search(fold(text))
