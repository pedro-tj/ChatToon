"""The character window on the desktop, display modes, section resets and compatibility with
ChatToon 2.3 settings (docs/ARCHITECTURE.md, docs/ARCHITECTURE.md). Offscreen: the compositor parts (KWin, Wayland)
are checked live by hand, see docs/DEVELOPMENT.md."""

import json

from PySide6.QtCore import Qt

from chattoon.core.config import Settings
from chattoon.gui import kwin

from .test_gui import backend, pump, qapp  # noqa: F401 - shared fixtures


def open_app(backend):  # noqa: F811 - shared fixture
    from chattoon.gui.app import create_engine

    warnings = []
    engine = create_engine(backend, warnings)
    pump(0.3)
    return engine, warnings


def test_window_opens_with_the_character_and_closes_alone(backend):  # noqa: F811 - shared fixture
    engine, warnings = open_app(backend)
    ctl = backend.window
    backend.setDisplayMode("window")
    assert pump(2, lambda: ctl.isOpen)
    win = ctl._window
    assert win.title() == "Minhoca — ChatToon" and not win.icon().isNull()
    assert win.flags() & Qt.WindowType.FramelessWindowHint
    assert (win.width(), win.height()) == (440, 660)
    assert "role=desktop" in ctl.url and ctl.url.startswith(backend.runtimeState["overlayUrl"])
    assert Settings.load().display.mode == "window" and Settings.load().display.window_open

    backend.selectCharacter("tux")
    assert pump(1, lambda: ctl.title == "Tux — ChatToon")
    ctl.setSize("small")
    assert (win.width(), win.height()) == (320, 480) and Settings.load().display.size == "small"
    ctl.setClickThrough(True)
    assert ctl._window.flags() & Qt.WindowType.WindowTransparentForInput and ctl.isOpen
    ctl.setClickThrough(False)
    assert not ctl._window.flags() & Qt.WindowType.WindowTransparentForInput
    ctl.scaleBy(1.5)
    assert win.height() == int(win.width() * 1.5) and Settings.load().display.size == "custom"

    # the right-click menu: inside the window when it fits, and the whole window takes the mouse
    from PySide6.QtCore import Q_ARG, QMetaObject, QObject
    ctl.setSize("medium")
    menu = ctl._window.findChild(QObject, "characterMenu")
    QMetaObject.invokeMethod(menu, "openAt", Q_ARG("QVariant", 400), Q_ARG("QVariant", 300))
    assert pump(1, lambda: menu.property("opened"))
    assert menu.property("x") + menu.property("width") <= ctl._window.width()  # kept inside
    assert ctl._window.mask().boundingRect().size() == ctl._window.size()
    menu.setProperty("visible", False)
    assert pump(1, lambda: ctl._window.mask().boundingRect().size() != ctl._window.size())

    ctl.hide()  # only the window: ChatToon goes on
    assert not ctl.isOpen and not Settings.load().display.window_open
    assert backend.runtimeState["overlayUrl"]
    backend.setDisplayMode("both")
    assert pump(1, lambda: ctl.isOpen)
    backend.setDisplayMode("obs")
    assert not ctl.isOpen
    ctl.shutdown()
    del engine
    assert warnings == []


def test_capabilities_are_detected_not_assumed(backend):  # noqa: F811 - shared fixture
    caps = backend.window.capabilities  # offscreen: no compositor at all
    assert caps["platform"] == "offscreen"
    assert not any(caps[k] for k in ("keepAbove", "position", "clickThrough", "kwin", "transparent"))


def test_kwin_script_matches_only_our_window_and_reports_geometry():
    script = kwin.SCRIPT % {"title": json.dumps('Tux "the" — ChatToon'), "pid": 1234, "state": json.dumps({"keepAbove": True}),
                            "service": json.dumps(":1.5"), "path": json.dumps(kwin.OBJECT_PATH),
                            "iface": json.dumps(kwin.INTERFACE)}
    assert 'const TITLE = "Tux \\"the\\" \\u2014 ChatToon", PID = 1234' in script  # quoted as JSON, never raw
    assert "w.pid === PID && w.caption === TITLE" in script and "callDBus(SERVICE" in script
    got = []
    bridge = kwin.KWinBridge.__new__(kwin.KWinBridge)
    kwin.QObject.__init__(bridge)
    bridge.geometryReported.connect(got.append)
    bridge.geometry('{"x": 10, "y": 20, "width": 400, "height": 600, "output": "DP-1", "evil": 1}')
    bridge.geometry("not json")
    assert got == [{"x": 10, "y": 20, "width": 400, "height": 600, "output": "DP-1"}]


def test_restore_one_section_keeps_everything_else(backend):  # noqa: F811 - shared fixture
    backend.setConfig("ai.temperature", 0.2)
    backend.setConfig("ai.model", "gemma3:4b")
    backend.setConfig("overlay.scale", 2.0)
    token = backend.settings.overlay.token
    backend.resetSection("ai.generation")
    s = Settings.load()
    assert s.ai.temperature == 0.9 and s.ai.model == "gemma3:4b" and s.overlay.scale == 2.0
    backend.resetSection("overlay.appearance")
    assert Settings.load().overlay.scale == 1.0 and Settings.load().overlay.token == token
    backend.resetSection("nonsense")  # ignored


def test_settings_and_profiles_of_chattoon_2_3_still_load(tmp_path):
    old = {"character": "owl", "mode": "auto", "theme": "dark", "first_run_done": True,
           "ai": {"host": "http://127.0.0.1:11434", "model": "qwen3.5:2b"},
           "overlay": {"port": 8765, "token": "keep-this-token", "public_address": "https://x.example.org:8443"},
           "voice": {"enabled": True, "volume": 50, "audio_output": "overlay"},
           "streams": {"sources": [{"id": "twitch-abc123", "platform": "twitch", "target": "ana"}], "migrated": True},
           "reading": {"mode": "name"}}
    path = tmp_path / "settings.json"
    path.write_text(json.dumps(old))
    original = path.read_bytes()
    s = Settings.load(path)
    backup = tmp_path / "settings.json.v2.bak"
    assert backup.read_bytes() == original and (backup.stat().st_mode & 0o777) == 0o600  # kept as it was
    assert s.config_version == 3
    s.save(path)
    assert Settings.load(path).config_version == 3 and backup.read_bytes() == original  # backed up once only
    assert (s.character, s.ai.model, s.overlay.token, s.overlay.public_address) == ("owl", "qwen3.5:2b", "keep-this-token",
                                                                                     "https://x.example.org:8443")
    assert s.display.mode == "obs" and not s.overlay.lan_enabled  # new features start off
    assert s.privacy_mode and not s.advanced
    assert s.stream_sources()[0].target == "ana"
    s.overlay.lan_enabled, s.overlay.lan_address = True, "192.168.0.2"
    profile = s.export_profile()
    assert "lan_address" not in profile["settings"]["overlay"] and "token" not in profile["settings"]["overlay"]
    other = Settings()
    imported = other.import_profile(profile)
    assert imported.overlay.token == other.overlay.token and imported.overlay.lan_enabled is False


def test_main_window_in_advanced_mode_and_privacy_off_has_no_warnings(backend):  # noqa: F811 - shared fixture
    backend.setConfig("advanced", True)
    backend.setConfig("privacy_mode", False)
    engine, warnings = open_app(backend)
    window = engine.rootObjects()[0]
    for page in range(11):
        window.setProperty("currentPage", page)
        pump(0.15)
    backend.sessionReport.check()
    assert pump(5, lambda: backend.sessionReport.report.get("state") in ("checked", "blocked"))
    report = backend.sessionReport.report
    assert report["ai"]["model"] == "gemma3:4b" and report["character"]["id"] == "worm"
    window.close()
    del engine
    assert warnings == []


def test_geometry_from_dbus_is_validated():
    got = []
    bridge = kwin.KWinBridge.__new__(kwin.KWinBridge)
    kwin.QObject.__init__(bridge)
    bridge.geometryReported.connect(got.append)
    bridge.geometry('{"x": "1; rm", "y": 2}')  # not numbers: ignored
    bridge.geometry('{"x": true, "y": 2}')
    bridge.geometry('{"x": 1e9, "y": 2}')
    bridge.geometry('{"x": 5, "y": 6, "output": 7}')
    assert got == [{"x": 5, "y": 6}]
