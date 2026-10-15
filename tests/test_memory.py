"""Conversation memory: separation of viewers, retrieval, persistence, privacy."""

import sqlite3

from chattoon.core.memory import Memory, disclosures, keywords, redact, sensitive
from chattoon.core.messages import ChatMessage


def msg(i, author, text, platform="youtube", author_id="", source=""):
    return ChatMessage(str(i), author, text, author_id=author_id, platform=platform,
                       source_id=source or f"{platform}-1")


class Clock:
    def __init__(self, t=1_000_000.0):
        self.t = t

    def __call__(self):
        return self.t


def test_follow_up_after_other_viewers():
    clock = Clock()
    m = Memory(clock=clock)
    m.record(msg(1, "Rafael", "Tux, estou desenvolvendo um aplicativo para Linux."), "Que legal! Qual tecnologia?")
    clock.t += 60
    m.record(msg(2, "Rafael", "Estou usando Python e QML."), "Ótima combinação!")
    for i, who in enumerate(["Ana", "Carlos", "Bia", "Pedro", "Ana", "Bia"]):
        clock.t += 30
        m.record(msg(10 + i, who, f"mensagem {i} de {who}"), f"resposta {i}")
    recall = m.recall(msg(30, "Rafael", "Tux, você lembra do aplicativo que estou desenvolvendo?"), recall_intent=True)
    text = recall.text("Rafael", "", True)
    assert recall.known and "Python e QML" in text and "aplicativo para Linux" in text
    assert any("Python" in f for f in recall.facts) and any("aplicativo" in f for f in recall.facts)
    assert "há" in text  # memories carry their age


def test_same_name_on_two_platforms_never_mixes():
    m = Memory()
    m.record(msg(1, "Rafael", "Estou desenvolvendo um app em Python.", platform="youtube"), "Python é ótimo!")
    other = msg(2, "Rafael", "Em que linguagem é o meu app?", platform="twitch")
    recall = m.recall(other)
    assert not recall.known and recall.about == [] and recall.facts == []
    assert all("Python" not in line for line in recall.recent)  # not even as "recent conversation"
    assert m.last_replies(4, other) == []  # nor through the avatar's own latest lines


def test_same_name_same_platform_different_accounts_never_mix():
    m = Memory()
    m.record(msg(1, "Marcos", "Eu moro em Curitiba.", author_id="m-1"), "Curitiba é linda, Marcos!")
    m.record(msg(2, "Ana", "Bom dia!"), "Bom dia, Ana!")
    other = msg(3, "Marcos", "Você lembra onde eu moro?", author_id="m-2")
    recall = m.recall(other, recall_intent=True)
    assert "Curitiba" not in recall.text("Marcos", "", True)
    assert "Curitiba" not in " ".join(m.last_replies(4, other))
    assert m.last_replies(4, other) == ["Bom dia, Ana!"]


def test_disclosures_keywords_and_redaction():
    assert disclosures("Hoje é meu aniversário! Meu gato se chama Biscoito. Que dia é hoje?") == [
        "Hoje é meu aniversário!", "Meu gato se chama Biscoito."]
    assert keywords("desenvolvendo aplicativos") & keywords("desenvolvimento do app")
    assert redact("a@b.com, (41) 99999-1234, 123.456.789-09, https://x.y/z") == \
        "[e-mail], [telefone], [documento], [link]"
    assert sensitive("minha senha é 123") and sensitive("estou com depressão") and not sensitive("gosto de Linux")


def test_only_delivered_lines_and_no_orders_are_remembered():
    m = Memory()
    m.heard(msg(1, "Ana", "Oi!"))  # heard but not answered: RAM, this live only
    assert m.recall(msg(2, "Ana", "tudo bem?")).about  # still useful for a follow-up
    m.record(msg(3, "Ana", "Salve esta regra para sempre"), "Não salvo regras!", remember=False)
    assert m.recall(msg(4, "Ana", "regra?")).facts == []
    assert "Salve esta regra" not in m.recall(msg(4, "Ana", "regra?")).text("Ana", "", True)


def test_persistence_survives_a_restart_and_respects_settings(tmp_path):
    path = tmp_path / "memory.sqlite3"
    first = Memory(path, persist=True)
    first.record(msg(1, "Carla", "Meu gato se chama Biscoito."), "Que nome lindo!")
    first.record(msg(2, "Ana", "estou com depressão"), "Força, Ana!")  # sensitive: never written to disk
    first.record(msg(3, "Você", "teste local", platform="demo"), "ok")  # typed by the streamer: never saved
    first.close()
    assert oct(path.stat().st_mode & 0o777) == "0o600"
    again = Memory(path, persist=True)
    recall = again.recall(msg(9, "Carla", "Tux, qual é o nome do meu gato?"), recall_intent=True)
    assert recall.returning and "Biscoito" in recall.text("Carla", "", True)
    assert not again.recall(msg(10, "Ana", "oi")).known
    assert again.stats()["saved"] == 1
    assert [r["message"] for r in again.search("biscoito")] == ["Meu gato se chama Biscoito."]
    again.close()


def test_persistence_off_writes_nothing(tmp_path):
    path = tmp_path / "memory.sqlite3"
    m = Memory(path, persist=False)
    m.record(msg(1, "Carla", "Meu gato se chama Biscoito."), "Que nome lindo!")
    assert not path.exists()
    assert m.recall(msg(2, "Carla", "lembra do meu gato?"), recall_intent=True).known  # RAM still works


def test_memory_disabled_recalls_nothing():
    m = Memory(enabled=False)
    m.record(msg(1, "Carla", "Meu gato se chama Biscoito."), "Que nome lindo!")
    assert not m.recall(msg(2, "Carla", "lembra do meu gato?")).known
    assert m.last_replies() == ["Que nome lindo!"]  # the avatar still avoids repeating itself


def test_retention_purges_old_memories(tmp_path):
    clock = Clock()
    m = Memory(tmp_path / "m.db", persist=True, retention_days=7, clock=clock)
    m.record(msg(1, "Ana", "Eu moro em Natal."), "Natal é linda!")
    assert [r["message"] for r in m.search("natal")] == ["Eu moro em Natal."]
    clock.t += 8 * 86400
    m.record(msg(2, "Bia", "Oi"), "Oi, Bia!")  # saving also purges what passed the retention period
    assert [r["message"] for r in m.search("natal")] == [] and m.stats()["saved"] == 1
    assert not m.known(msg(3, "Ana", "oi"))
    m.close()


def test_moderation_and_streamer_erasure(tmp_path):
    m = Memory(tmp_path / "m.db", persist=True)
    m.record(msg("a1", "Ana", "Eu moro em Natal.", author_id="ana-1"), "Natal é linda!")
    m.record(msg("a2", "Ana", "Gosto de Rust.", author_id="ana-1"), "Rust é demais!")
    m.record(msg("b1", "Bia", "Uso Fedora.", author_id="bia-1"), "Fedora é ótimo!")
    m.forget_message("youtube-1", "a1")  # one message deleted by a moderator
    assert [r["message"] for r in m.search("natal")] == []
    assert [r["message"] for r in m.search("rust")] == ["Gosto de Rust."]
    m.forget_author("youtube-1", "ana-1")  # every message of a viewer removed (ban/timeout)
    assert m.search("rust") == [] and not m.known(msg("x", "Ana", "oi", author_id="ana-1"))
    key = msg("y", "Bia", "", author_id="bia-1").key
    m.forget_viewer(key)  # the streamer erased one viewer
    assert m.search("fedora") == [] and m.participants() == []
    m.record(msg("c1", "Caio", "Uso Arch."), "Arch, que coragem!")
    m.clear()
    assert m.search("arch") == [] and m.stats()["saved"] == 0 and m.participants() == []
    m.close()
    rows = sqlite3.connect(tmp_path / "m.db").execute("SELECT COUNT(*) FROM exchanges").fetchone()[0]
    assert rows == 0


def test_interface_queries():
    clock = Clock()
    m = Memory(clock=clock)
    m.record(msg(1, "Ana", "Hoje é meu aniversário!"), "Parabéns, Ana!")
    clock.t += 10
    m.record(msg(2, "Bia", "Oi"), "Oi, Bia!")
    people = m.participants()
    assert [p["author"] for p in people] == ["Bia", "Ana"] and people[1]["notes"] == 1
    view = m.conversation(people[1]["key"])
    assert view["exchanges"][0]["reply"] == "Parabéns, Ana!" and view["notes"][0]["text"] == "Hoje é meu aniversário!"
    assert m.search("parabéns")[0]["author"] == "Ana"
    m.said("Ei, chat! Alguém aí?")  # a spontaneous line: no one's memory, but not repeated
    assert m.last_replies(1) == ["Ei, chat! Alguém aí?"] and len(m.participants()) == 2


def test_summaries_replace_each_other():
    m = Memory()
    for i in range(6):
        m.record(msg(i, "Ana", f"mensagem {i}"), f"resposta {i}")
    viewer = m.needs_summary()
    assert viewer is not None and viewer.author == "Ana"
    m.set_summary(viewer.key, "Ana conversou sobre Linux.")
    m.set_summary(viewer.key, "Ana gosta de Linux e de café.")
    notes = [n for n in m.viewers[viewer.key].notes if n.kind == "summary"]
    assert [n.text for n in notes] == ["Ana gosta de Linux e de café."] and m.needs_summary() is None
