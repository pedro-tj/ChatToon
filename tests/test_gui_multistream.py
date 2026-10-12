"""Desktop app: sources management, accounts, unified feed and the new pages."""

import json

from chattoon.core.config import Settings
from chattoon.gui.feed import ChatFeedFilter, ChatFeedModel, row_from_message

from .test_gui import backend, pump, qapp  # noqa: F401 - fixtures


def test_add_edit_remove_sources_and_reject_duplicates(backend):  # noqa: F811
    assert backend.detectSource("https://www.twitch.tv/Canal_Linux", "", "")["platform"] == "twitch"
    assert backend.detectSource("canal", "", "")["code"] == "ambiguous"
    tw = backend.addSource("twitch", "https://www.twitch.tv/canal_linux", "Principal", True, {"mode": "anonymous"})
    yt = backend.addSource("youtube", "https://youtu.be/AbCdEfGhIjK", "", True, {})
    assert tw and yt
    dup = backend.detectSource("twitch.tv/CANAL_LINUX", "twitch", "")
    assert dup["ok"] is False and dup["code"] == "duplicate"
    assert backend.addSource("twitch", "canal_linux", "", True, {}) == ""  # same chat twice
    assert backend.detectSource("twitch.tv/canal_linux", "twitch", tw)["ok"]  # editing itself is fine
    assert backend.addSource("twitch", "outro_canal", "", True, {})  # another channel is fine

    assert backend.updateSource(tw, {"priority": 4, "enabled": False, "options": {"mode": "account", "token": "x"}})
    saved = Settings.load()
    source = next(s for s in saved.streams.sources if s.id == tw)
    assert (source.priority, source.enabled, source.options) == (4, False, {"mode": "account"})  # no secrets kept
    assert pump(3, lambda: any(s["id"] == tw and s["status"]["state"] == "disabled" for s in backend.sources))
    backend.removeSource(yt)
    assert pump(3, lambda: all(s["id"] != yt for s in backend.sources))
    assert [s.id for s in Settings.load().streams.sources if s.id == yt] == []


def test_secrets_go_to_the_keyring_never_to_settings(backend):  # noqa: F811
    backend.setSecret("x/bearer", "bearer_token", "BEARER_SECRET_VALUE")
    backend.setSecret("not/allowed", "token", "nope")
    assert pump(3, lambda: backend.accounts.get("x", {}).get("token"))
    store = backend.engine.streams.ctx.credentials
    assert store.get("x/bearer") == {"bearer_token": "BEARER_SECRET_VALUE"} and store.get("not/allowed") is None
    assert "BEARER_SECRET_VALUE" not in Settings.file().read_text()
    assert "BEARER_SECRET_VALUE" not in json.dumps(backend.settings.export_profile())
    backend.clearSecret("x/bearer")
    assert pump(3, lambda: not backend.accounts["x"]["token"])


def test_feed_model_batches_updates_and_caps(qapp):  # noqa: F811
    model = ChatFeedModel(limit=50)
    proxy = ChatFeedFilter(model)
    rows = [row_from_message({"id": f"tw:{i}", "platform": "twitch" if i % 2 else "youtube", "author": f"u{i}",
                              "text": f"mensagem {i}", "dropped": "" if i % 5 else "repeated"}) for i in range(120)]
    model.append(rows[:60])
    model.append(rows[60:])
    assert model.rowCount() == 50 and model.counts == {"twitch": 25, "youtube": 25}  # counts follow the cap
    assert model.update("tw:119", status="answered", reply="Oi!") and not model.update("tw:0", status="x")  # capped out
    assert model.get("tw:119")["reply"] == "Oi!"
    proxy.platform = "twitch"
    assert proxy.rowCount() == 25
    proxy.platform = ""
    proxy.search = "MENSAGEM 11"
    assert proxy.rowCount() == 10  # 110…119: every word must appear (rows 0–69 left the list)
    proxy.search = ""
    proxy.hideDropped = True
    assert proxy.rowCount() == 40


def test_messages_from_the_engine_reach_the_feed_with_states(backend):  # noqa: F811
    backend.start()
    assert pump(3, lambda: backend.runtimeState["state"] == "running")
    backend.submitMessage("oi tux", "Ana")
    assert pump(8, lambda: backend.feedModel.total == 1 and backend.feedModel.get(
        backend.feedModel._rows[0]["uid"])["status"] == "answered")
    row = backend.feedModel._rows[0]
    assert row["author"] == "Ana" and row["reply"].startswith("Resposta para")


def test_platform_pages_load_with_sources_and_dialog(backend):  # noqa: F811
    from chattoon.gui.app import create_engine

    backend.addSource("twitch", "canal_linux", "", True, {})
    backend.addSource("kick", "kick.com/canal", "Kick principal", False, {"mode": "pusher", "chatroom_id": "123"})
    backend.submitMessage("primeira mensagem", "Bia")
    warnings = []
    engine = create_engine(backend, warnings)
    window = engine.rootObjects()[0]
    for page in (0, 4, 5, 10):
        window.setProperty("currentPage", page)
        pump(0.3)
    window.setProperty("currentPage", 4)
    pump(0.2)

    from PySide6.QtCore import Q_ARG, QMetaObject, QObject

    dialog = window.findChild(QObject, "sourceDialog")
    assert dialog is not None
    QMetaObject.invokeMethod(dialog, "openNew", Q_ARG("QVariant", "tiktok"))
    pump(0.3)
    assert dialog.property("visible") and dialog.property("platform") == "tiktok"
    dialog.setProperty("platform", "youtube")
    pump(0.2)

    backend.setConfig("chat.selection", "weighted")
    backend.setConfig("theme", "light")
    pump(0.3)
    window.close()
    del engine
    assert warnings == []
