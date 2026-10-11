import json
import random

import pytest

from chattoon.core.config import Personality, Settings, from_dict
from chattoon.core.messages import ChatMessage, MessageSelector, SelectorConfig, clean_text, mentions


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def msg(i, author="ana", text="oi", **kw):
    return ChatMessage(id=f"m{i}", author=author, author_id=author, text=text, **kw)


def selector(mode="smart", **kw):
    clock = Clock()
    cfg = SelectorConfig(mode=mode, names=("minhoca", "worm"), **kw)
    return MessageSelector(cfg, clock=clock, rng=random.Random(1)), clock


# -- config -------------------------------------------------------------

def test_settings_roundtrip_and_permissions(tmp_path):
    s = Settings()
    s.ai.model = "gemma3:4b"
    s.character_settings("tux").personality.humor = 12
    path = tmp_path / "s.json"
    s.save(path)
    assert oct(path.stat().st_mode & 0o777) == "0o600"
    loaded = Settings.load(path)
    assert loaded.ai.model == "gemma3:4b"
    assert loaded.characters["tux"].personality.humor == 12
    assert loaded.overlay.token == s.overlay.token


def test_settings_tolerate_garbage(tmp_path):
    path = tmp_path / "s.json"
    path.write_text(json.dumps({"character": 5, "ai": {"temperature": "hot", "model": "x"},
                                "chat": "nope", "unknown": 1, "characters": {"worm": {"voice_rate": True}}}))
    s = Settings.load(path)
    assert s.character == "worm" and s.ai.model == "x" and s.ai.temperature == 0.9
    assert s.characters["worm"].voice_rate == 0
    (tmp_path / "bad.json").write_text("{")
    assert Settings.load(tmp_path / "bad.json").character == "worm"


def test_character_defaults_and_profiles():
    s = Settings()
    assert s.character_settings("worm").personality.preset == "troll"
    assert s.character_settings("tux").personality.geek == 95
    profile = s.export_profile()
    assert "token" not in profile["settings"]["overlay"]
    other = Settings()
    imported = other.import_profile(json.loads(json.dumps(profile)))
    assert imported.overlay.token == other.overlay.token  # secret stays local
    with pytest.raises(ValueError):
        other.import_profile({"foo": 1})


def test_from_dict_nested_lists():
    p = from_dict(Personality, {"humor": 10, "length": 3})
    assert p.humor == 10 and p.length == "short"


# -- messages -----------------------------------------------------------

def test_clean_text_strips_control_and_bidi():
    assert clean_text("oi‮\x00  tudo\n bem") == "oi tudo bem"
    assert clean_text("a" * 10 + " " + "b" * 400, 20).endswith("…")


def test_mentions_ignore_accents_and_word_boundaries():
    assert mentions("Ô MINHÓCA, bom dia", ("minhoca",))
    assert not mentions("minhocaria", ("minhoca",))


def test_dedup_by_id_and_repeat_spam():
    sel, clock = selector()
    assert sel.offer(msg(1, text="olá pessoal")) == ""
    assert sel.offer(msg(1, text="outro texto")) == "duplicate"
    assert sel.offer(msg(2, text="OLÁ  pessoal")) == "repeated"  # same person, same text
    assert sel.offer(msg(3, author="bia", text="olá pessoal")) == ""  # other person may say it
    clock.t += 31
    assert sel.offer(msg(4, text="olá pessoal")) == ""


def test_rejects_empty_commands_blocked():
    sel, _ = selector(blocked_words=("palavrão",))
    assert sel.offer(msg(1, text="😂😂")) == "empty"
    assert sel.offer(msg(2, text="!sorteio")) == "command"
    assert sel.offer(msg(3, text="que PALAVRÃO feio")) == "blocked word"


def test_smart_prefers_mentions_questions_and_superchat():
    sel, _ = selector()
    sel.offer(msg(1, "a", "legal"))
    sel.offer(msg(2, "b", "minhoca, você dorme?"))
    sel.offer(msg(3, "c", "bom dia"))
    sel.offer(msg(4, "d", "toma aqui", superchat="R$ 10,00"))
    assert [sel.next().id for _ in range(2)] == ["m4", "m2"]


def test_user_cooldown_and_superchat_bypass():
    sel, clock = selector(user_cooldown=60)
    sel.offer(msg(1, "ana", "primeira"))
    assert sel.next().id == "m1"
    sel.offer(msg(2, "ana", "segunda"))
    assert sel.next() is None  # still in cooldown
    sel.offer(msg(3, "ana", "pix", superchat="R$ 5"))
    assert sel.next().id == "m3"
    clock.t += 61
    assert sel.next().id == "m2"


def test_ttl_expiry_and_queue_limit():
    sel, clock = selector(ttl=30, max_queue=3)
    for i in range(5):
        sel.offer(msg(i, f"u{i}", f"mensagem {i}"))
    assert len(sel) == 3
    clock.t += 31
    assert sel.next() is None and len(sel) == 0


def test_no_starvation_old_messages_gain_priority():
    sel, clock = selector(ttl=100)
    sel.offer(msg(1, "old", "texto comum"))
    clock.t += 90
    sel.offer(msg(2, "new", "texto comum também"))
    assert sel.next().id == "m1"


def test_modes():
    sel, _ = selector("mentions")
    assert sel.offer(msg(1, text="sem citar ninguém")) == "no mention"
    assert sel.offer(msg(2, text="e aí Worm")) == ""

    sel, _ = selector("all")
    for i in range(3):
        sel.offer(msg(i, f"u{i}", f"texto {i}"))
    assert [sel.next().id for _ in range(3)] == ["m0", "m1", "m2"]

    sel, _ = selector("moderators")
    sel.offer(msg(1, "a", "minhoca? oi?"))
    sel.offer(msg(2, "mod", "texto", is_moderator=True))
    assert sel.next().id == "m2"

    sel, _ = selector("manual")
    sel.offer(msg(1, "a", "x y"))
    assert sel.next() is None
    assert sel.take("m1").id == "m1" and len(sel) == 0
