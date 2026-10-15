"""The face that goes with a line: the model's emotion, checked against what was said.

The model picks an emotion with every reply, but small models fall into habits (the
original prompt made almost every line "laugh"). The controller keeps the model's choice
when it fits the kind of message, replaces it when it does not (no laughing at someone
who is sad, no party for "what is a CPU?"), avoids the same strong emotion over and over,
and adds a *lead*: a quick first reaction played before the line's own emotion —
surprised, then celebrating good news. No extra model call is involved.
"""

from __future__ import annotations

from dataclasses import dataclass

from .characters import EMOTIONS
from .intent import Intent

STRONG = ("laugh", "celebrate", "annoyed", "surprised")


@dataclass
class Feeling:
    emotion: str
    intensity: float
    lead: str = ""  # played first, for about a second

    def to_dict(self) -> dict:
        return {"emotion": self.emotion, "intensity": round(self.intensity, 2), "lead": self.lead}


def choose(intent: Intent | None, emotion: str, intensity: float, recent: list[str] | None = None) -> Feeling:
    """Final emotion for a reply. ``recent``: emotions of the latest lines spoken."""
    emotion = emotion if emotion in EMOTIONS else "neutral"
    intensity = min(1.0, max(0.2, float(intensity) if intensity == intensity else 0.5))
    if intent is None:
        return Feeling(emotion, intensity)
    allowed = intent.emotions
    if allowed and emotion not in allowed:
        emotion = intent.emotion or allowed[0]
        intensity = min(intensity, 0.7) if emotion not in ("celebrate",) else max(intensity, 0.7)
    recent = [e for e in (recent or []) if e]
    # the same strong emotion three times in a row looks like a tic, not a reaction
    if emotion in STRONG and len(recent) >= 2 and recent[-1] == recent[-2] == emotion and \
            not (allowed and allowed[0] == emotion and intent.kind in ("joke", "good_news")):
        emotion = "happy" if emotion in ("laugh", "celebrate") else "neutral"
        intensity = min(intensity, 0.6)
    if intent.kind == "sad":
        intensity = min(intensity, 0.5)  # gentle face for someone who is not well
    if intent.objective:
        intensity = min(intensity, 0.7)
    lead = intent.lead if intent.lead and intent.lead != emotion else ""
    return Feeling(emotion, round(intensity, 2), lead)
