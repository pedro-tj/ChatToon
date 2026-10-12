"""Reading the viewer's name and message aloud before the reply.

What is read is the viewer's own text, never something the AI wrote: it is only
normalised for speech (links, emoji, repeated letters, invisible characters, odd user
names) and cut at a word boundary when it is too long. The AI receives the message
exactly as before, inside its delimited data block, so the reading cannot change the
model's instructions either.
"""

from __future__ import annotations

import re
import unicodedata
import zlib
from dataclasses import dataclass

from .messages import ChatMessage, clean_text

READING_MODES = ("off", "name", "name_message")

_TEMPLATES = {
    "pt": {
        "said": "{name} disse: {text}",
        "asked": "{name} perguntou: {text}",
        "superchat": "{name} mandou um Super Chat de {amount} e disse: {text}",
        "paid": "{name} mandou {amount} e disse: {text}",
        "name": "Mensagem de {name}.",
        "name_question": "Pergunta de {name}.",
        "name_superchat": "Super Chat de {name}!",
        "name_paid": "{name} mandou {amount}!",
        "viewer": "um espectador",
        "link": "link",
        # with the platform ({at}: "na Twitch", {of}: "da Twitch"); a few variations so a
        # busy multistream does not sound like a robot reading a log
        "p_said": ("{At}, {name} disse: {text}", "Direto {of}, {name} disse: {text}",
                   "{name}, lá {of}, disse: {text}"),
        "p_asked": ("{At}, {name} perguntou: {text}", "Direto {of}, {name} quer saber: {text}",
                    "{name}, lá {of}, perguntou: {text}"),
        "p_superchat": ("{At}, {name} mandou um Super Chat de {amount} e disse: {text}",),
        "p_paid": ("{At}, {name} mandou {amount} e disse: {text}",),
        "p_name": ("Mensagem de {name}, {at}.", "Mensagem {of}, de {name}."),
        "p_name_question": ("Pergunta de {name}, {at}.", "Pergunta {of}, de {name}."),
        "p_name_superchat": ("Super Chat de {name}, {at}!",),
        "p_name_paid": ("{At}, {name} mandou {amount}!",),
        "event_subscription": "{name} virou membro{at_tail}!",
        "event_gift": "{name} mandou um presente{at_tail}: {amount}!",
        "event_follow": "{name} começou a seguir{at_tail}!",
        "event_raid": "{name} chegou com uma raid{at_tail}!",
    },
    "en": {
        "said": "{name} said: {text}",
        "asked": "{name} asked: {text}",
        "superchat": "{name} sent a {amount} Super Chat: {text}",
        "paid": "{name} sent {amount}: {text}",
        "name": "Message from {name}.",
        "name_question": "Question from {name}.",
        "name_superchat": "Super Chat from {name}!",
        "name_paid": "{name} sent {amount}!",
        "viewer": "a viewer",
        "link": "link",
        "p_said": ("{At}, {name} said: {text}", "Straight from {label}, {name} said: {text}",
                   "{name}, over {at}, said: {text}"),
        "p_asked": ("{At}, {name} asked: {text}", "Straight from {label}, {name} wants to know: {text}",
                    "{name}, over {at}, asked: {text}"),
        "p_superchat": ("{At}, {name} sent a {amount} Super Chat: {text}",),
        "p_paid": ("{At}, {name} sent {amount}: {text}",),
        "p_name": ("Message from {name}, {at}.", "A message {of}, from {name}."),
        "p_name_question": ("Question from {name}, {at}.", "A question {of}, from {name}."),
        "p_name_superchat": ("Super Chat from {name}, {at}!",),
        "p_name_paid": ("{At}, {name} sent {amount}!",),
        "event_subscription": "{name} just subscribed{at_tail}!",
        "event_gift": "{name} sent a gift{at_tail}: {amount}!",
        "event_follow": "{name} just followed{at_tail}!",
        "event_raid": "{name} arrived with a raid{at_tail}!",
    },
}

# how each platform is said in a sentence: (at, of)
_PLATFORM_WORDS = {
    "pt": {"youtube": ("no YouTube", "do YouTube"), "twitch": ("na Twitch", "da Twitch"),
           "kick": ("na Kick", "da Kick"), "tiktok": ("no TikTok", "do TikTok"),
           "facebook": ("no Facebook", "do Facebook"), "instagram": ("no Instagram", "do Instagram"),
           "x": ("no X", "do X")},
    "en": {p: (f"on {n}", f"from {n}") for p, n in (
        ("youtube", "YouTube"), ("twitch", "Twitch"), ("kick", "Kick"), ("tiktok", "TikTok"),
        ("facebook", "Facebook"), ("instagram", "Instagram"), ("x", "X"))},
}
_LABELS = {"youtube": "YouTube", "twitch": "Twitch", "kick": "Kick", "tiktok": "TikTok", "facebook": "Facebook",
           "instagram": "Instagram", "x": "X"}

_URL = re.compile(r"(?:https?://|www\.)\S+|\b[\w-]+\.(?:com|net|org|br|io|tv|gg|ly|me|app|dev)(?:/\S*)?\b", re.I)
_EMOJI = re.compile(r"[\U0001F000-\U0001FAFF☀-➿⬀-⯿️‍⃣]")
_SHORTCODE = re.compile(r":[a-z0-9_+-]{2,40}:", re.I)  # YouTube emoji shortcodes (:face-blue-smiling:)
_REPEAT = re.compile(r"(\w)\1{3,}")  # "siiiiiim" -> "siiim", "kkkkkkk" -> "kkk"
_PUNCT_RUN = re.compile(r"([!?.…])[!?.…]{1,}")
_DEFAULT_HANDLE = re.compile(r"^user[\s-]?[a-z0-9]{6,}$", re.I)  # YouTube's generated @user-xxxx
_RANDOM_TOKEN = re.compile(r"^(?=\w*\d\w*\d\w*\d)(?=\w*[a-z])\w{6,}$", re.I)  # "ab12cd34"


@dataclass(frozen=True)
class Reading:
    author: str  # display name (speech bubble)
    text: str  # message shown in the bubble (cleaned and cut like what is read)
    spoken: str  # exactly what the voice says
    mode: str  # name | name_message
    question: bool = False
    superchat: str = ""
    platform: str = ""  # set when the platform is announced

    def to_dict(self) -> dict:
        return {"author": self.author, "text": self.text, "spoken": self.spoken, "mode": self.mode,
                "question": self.question, "superchat": self.superchat, "platform": self.platform}


def _lang(language: str) -> dict:
    return _TEMPLATES["pt" if language.lower().startswith("pt") else "en"]


def _pick(options, msg: ChatMessage) -> str:
    """A variation chosen by the message id: varied over a live, stable for one message."""
    if isinstance(options, str):
        return options
    return options[zlib.crc32(msg.uid.encode()) % len(options)]


def _fill(template: str, **values) -> str:
    text = template.format(**values)
    return text[:1].upper() + text[1:]


def speakable_name(author: str, language: str = "pt-BR") -> str:
    """A user name a voice can say: "@joao_linux1987" -> "joao linux", "JoaoLinux" -> "Joao Linux"."""
    name = unicodedata.normalize("NFKC", clean_text(author or "", 80))  # 𝓙𝓸𝓪𝓸 -> Joao
    name = _EMOJI.sub(" ", _SHORTCODE.sub(" ", name)).strip().lstrip("@")
    if _DEFAULT_HANDLE.match(name):
        return _lang(language)["viewer"]
    name = re.sub(r"[_.|/\\~^*=+#<>\[\]{}()\"`-]+", " ", name)
    name = re.sub(r"(?<=[a-zà-ÿ])(?=[A-ZÀ-Ý][a-zà-ÿ])", " ", name)  # camelCase
    name = re.sub(r"(?<=[^\W\d])\d{3,}\b", " ", name)  # trailing digit runs: joao1987 -> joao
    words = [w for w in name.split() if not _RANDOM_TOKEN.match(w)]
    name = _REPEAT.sub(r"\1\1\1", " ".join(words[:4]))[:40].strip(" '")
    if not any(c.isalpha() for c in name):
        return _lang(language)["viewer"]
    return name


def speakable_text(text: str, language: str = "pt-BR") -> str:
    """The viewer's message prepared for a voice: same words, minus things voices garble."""
    words = _lang(language)
    text = clean_text(text or "", 2000)
    text = _URL.sub(f" {words['link']} ", text)
    text = _EMOJI.sub(" ", _SHORTCODE.sub(" ", text))
    text = re.sub(r"(?<!\w)[@#](\w)", r"\1", text)  # @mentions and #hashtags: just the word
    text = _REPEAT.sub(r"\1\1\1", text)
    text = _PUNCT_RUN.sub(lambda m: "?" if "?" in m.group() else ("!" if "!" in m.group() else "…"), text)
    text = re.sub(r"[*_`~<>|^\\]+", " ", text)
    text = re.sub(r"\s+([,.!?…;:])", r"\1", " ".join(text.split()))
    return text.strip(" ,;:")


def display_text(text: str) -> str:
    """The message as shown in the overlay bubble: links hidden, the rest untouched."""
    return " ".join(_URL.sub("🔗", clean_text(text or "", 2000)).split())


def cut(text: str, limit: int) -> str:
    """Shorten at a sentence or word boundary. Never rewrites or summarises the words."""
    limit = max(20, int(limit))
    if len(text) <= limit:
        return text
    head = text[:limit]
    end = max(head.rfind(p) for p in ".!?…")
    if end >= limit * 0.45:  # a whole sentence reads better than a cut one
        return head[:end + 1]
    return head.rsplit(" ", 1)[0].rstrip(" ,;:") + "…"


def build_reading(msg: ChatMessage, mode: str, max_chars: int, language: str,
                  announce_platform: bool = False) -> Reading | None:
    """The line read before the reply, or None when reading is off or there is nothing to read.

    ``announce_platform`` adds where the message came from ("Na Twitch, Ana perguntou: …");
    the viewer's words themselves are never changed."""
    if mode not in ("name", "name_message"):
        return None
    words = _lang(language)
    lang = "pt" if language.lower().startswith("pt") else "en"
    name = speakable_name(msg.author, language)
    shown = cut(display_text(msg.text), max_chars)
    spoken_text = cut(speakable_text(msg.text, language), max_chars)
    question = msg.is_question
    platform = msg.platform if announce_platform and msg.platform in _LABELS else ""
    at, of = _PLATFORM_WORDS[lang].get(platform, ("", ""))
    values = {"name": name, "amount": msg.superchat, "at": at, "At": at, "of": of, "label": _LABELS.get(platform, ""),
              "at_tail": f" {at}" if at else ""}
    if msg.event_type in ("subscription", "gift", "follow", "raid") and not has_words(msg.text):
        spoken = _fill(words[f"event_{msg.event_type}"], **values)
        return Reading(author=clean_text(msg.author, 60), text=msg.superchat or "", spoken=spoken, mode="name",
                       question=False, superchat=msg.superchat, platform=platform)
    if not any(c.isalnum() for c in speakable_text(_URL.sub(" ", msg.text), language)):
        mode = "name"  # only emoji or links: say who wrote, not "link link link"
    paid = "superchat" if msg.is_superchat else "paid"
    prefix = "p_" if platform else ""
    if mode == "name":
        key = f"name_{paid}" if msg.is_paid else ("name_question" if question else "name")
        spoken = _fill(_pick(words[prefix + key], msg), **values)
    else:
        key = paid if msg.is_paid else ("asked" if question else "said")
        if spoken_text[-1:] not in ".!?…":
            spoken_text += "."
        spoken = _fill(_pick(words[prefix + key], msg), text=spoken_text, **values)
    return Reading(author=clean_text(msg.author, 60), text=shown, spoken=spoken, mode=mode,
                   question=question, superchat=msg.superchat if msg.is_paid else "", platform=platform)


def has_words(text: str) -> bool:
    return any(c.isalnum() for c in text or "")
