"""KWin window rules from a script, for the character window (docs/30-wayland-floating-window.md).

Wayland lets no client place itself, stay above other windows or leave the taskbar — the
compositor decides. KDE's compositor, KWin, runs small JavaScript programs loaded over
D-Bus (``org.kde.KWin /Scripting``), with the person's own rights: no password, nothing
installed, gone when the session ends. ChatToon loads one that finds its character window
(by process id and exact title), applies keep-above / skip-taskbar / position, and reports
the geometry back over D-Bus so the position survives a restart. On other desktops, or when
scripting is off, this module simply reports "unavailable" and nothing is attempted.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from pathlib import Path

from PySide6.QtCore import ClassInfo, QObject, Signal, Slot

log = logging.getLogger(__name__)

PLUGIN = "chattoon-character-window"
OBJECT_PATH = "/ChatToon/CharacterWindow"
INTERFACE = "org.chattoon.CharacterWindow"

SCRIPT = """
const TITLE = %(title)s, PID = %(pid)d, STATE = %(state)s;
const SERVICE = %(service)s, PATH = %(path)s, IFACE = %(iface)s;
function ours(w) { return w && w.pid === PID && w.caption === TITLE; }
function report(w) {
    const g = w.frameGeometry;
    callDBus(SERVICE, PATH, IFACE, "geometry", JSON.stringify({
        x: Math.round(g.x), y: Math.round(g.y), width: Math.round(g.width), height: Math.round(g.height),
        output: w.output ? w.output.name : "", keepAbove: w.keepAbove }));
}
function apply(w) {
    if (STATE.keepAbove !== null) w.keepAbove = STATE.keepAbove;
    w.skipTaskbar = STATE.skipTaskbar;
    w.skipPager = STATE.skipTaskbar;
    w.skipSwitcher = false;
    const g = w.frameGeometry;
    if (STATE.place) {
        w.frameGeometry = { x: STATE.x, y: STATE.y, width: g.width, height: g.height };
    } else if (STATE.corner) {
        // first time: bottom-right corner of the usable area (panels excluded) of the active screen
        const area = workspace.clientArea(KWin.MaximizeArea, workspace.activeScreen, workspace.currentDesktop);
        w.frameGeometry = { x: area.x + area.width - g.width - 32, y: area.y + area.height - g.height - 24,
                            width: g.width, height: g.height };
    }
    w.frameGeometryChanged.connect(function () { report(w); });
    report(w);
}
workspace.windowList().forEach(function (w) { if (ours(w)) apply(w); });
workspace.windowAdded.connect(function (w) { if (ours(w)) apply(w); });
"""


@ClassInfo({"D-Bus Interface": INTERFACE})
class KWinBridge(QObject):
    """Loads the window script and receives the geometry it reports."""

    geometryReported = Signal("QVariantMap")

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.available = False
        self._service = ""
        self._loaded = False
        self._path: Path | None = None
        try:
            from PySide6.QtDBus import QDBusConnection, QDBusInterface
        except ImportError:  # Qt built without D-Bus
            return
        bus = QDBusConnection.sessionBus()
        if not bus.isConnected():
            return
        iface = bus.interface()
        if iface is None or not iface.isServiceRegistered("org.kde.KWin").value():
            return
        scripting = QDBusInterface("org.kde.KWin", "/Scripting", "org.kde.kwin.Scripting", bus)
        if not scripting.isValid():
            return
        if not bus.registerObject(OBJECT_PATH, self, QDBusConnection.RegisterOption.ExportAllSlots):
            log.info("cannot export the window bridge on D-Bus")
            return
        self._bus, self._scripting, self._iface_cls = bus, scripting, QDBusInterface
        self._service = bus.baseService()
        self.available = True

    @Slot(str)
    def geometry(self, payload: str) -> None:
        """Called by the KWin script (JSON with x, y, width, height, output)."""
        try:
            data = json.loads(payload)
        except ValueError:
            return
        if not isinstance(data, dict):
            return
        # any program of the session can call this slot: accept only well-formed numbers
        out = {k: int(data[k]) for k in ("x", "y", "width", "height")
               if isinstance(data.get(k), (int, float)) and not isinstance(data.get(k), bool) and abs(data[k]) < 100000}
        if isinstance(data.get("output"), str):
            out["output"] = data["output"][:64]
        if isinstance(data.get("keepAbove"), bool):
            out["keepAbove"] = data["keepAbove"]
        if {"x", "y"} <= out.keys():
            self.geometryReported.emit(out)

    def apply(self, title: str, state: dict) -> bool:
        """(Re)load the script for the window titled ``title`` with ``state``:
        keepAbove (bool|None), skipTaskbar (bool), place (bool), x, y, corner (bool: first placement)."""
        if not self.available:
            return False
        self.unload()
        script = SCRIPT % {"title": json.dumps(title), "pid": os.getpid(), "state": json.dumps(state),
                           "service": json.dumps(self._service), "path": json.dumps(OBJECT_PATH),
                           "iface": json.dumps(INTERFACE)}
        runtime = Path(os.environ.get("XDG_RUNTIME_DIR") or tempfile.gettempdir())
        fd, name = tempfile.mkstemp(prefix="chattoon-kwin-", suffix=".js", dir=runtime)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(script)
        self._path = Path(name)
        reply = self._scripting.call("loadScript", str(self._path), PLUGIN)
        args = reply.arguments()
        if reply.errorMessage() or not args or int(args[0]) < 0:
            log.info("KWin did not load the window script: %s", reply.errorMessage())
            self._remove_file()
            return False
        script_obj = self._iface_cls("org.kde.KWin", f"/Scripting/Script{int(args[0])}", "org.kde.kwin.Script",
                                     self._bus)
        script_obj.call("run")
        self._loaded = True
        return True

    def unload(self) -> None:
        if self.available and self._loaded:
            self._scripting.call("unloadScript", PLUGIN)
        self._loaded = False
        self._remove_file()

    def _remove_file(self) -> None:
        if self._path is not None:
            self._path.unlink(missing_ok=True)
            self._path = None
