"""The character on the desktop: a transparent, frameless window showing only the avatar
(docs/ARCHITECTURE.md).

It loads the same overlay page as OBS with ``role=desktop``: it watches the engine's events
(animations, expressions, speech bubble, lip sync) but never receives the audio, so a reply
is still heard exactly once — on this computer or in OBS, as the Voice page says.

What each session allows is detected, never assumed:
* transparency and dragging (``startSystemMove``): X11 with a compositor and every Wayland;
* clicks through the window: Qt's input-transparent flag (empty input region), X11 and Wayland;
* staying above, leaving the taskbar, a remembered position: X11 window flags, or KWin's
  scripting on KDE Plasma (Wayland and X11). Without KWin on Wayland these are unavailable
  and the interface says so.
"""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import Property, QObject, QRect, QTimer, QUrl, Signal, Slot
from PySide6.QtGui import QGuiApplication, QRegion
from PySide6.QtQml import QQmlComponent, QQmlEngine

from ..core.characters import CHARACTERS, get_character
from .icons import character_icon
from .kwin import KWinBridge

log = logging.getLogger(__name__)

QML = Path(__file__).resolve().parent / "qml" / "CharacterWindow.qml"
SIZES = {"small": (320, 480), "medium": (440, 660), "large": (600, 900)}
MIN_SIZE = (260, 390)


class CharacterWindow(QObject):
    changed = Signal()
    geometryChanged = Signal()

    def __init__(self, backend) -> None:
        super().__init__(backend)
        self.backend = backend
        self._engine = None
        self._window = None
        self._bridge: KWinBridge | None = None
        self._kwin_place = False  # next script load moves the window
        self._save = QTimer(self, singleShot=True, interval=800)
        self._save.timeout.connect(self._persist)
        self._pending_geometry: dict = {}
        self._menu_open = False
        self._character = backend.settings.character
        backend.configChanged.connect(self._on_config)

    # -- capabilities ---------------------------------------------------------------------

    @property
    def settings(self):
        return self.backend.settings.display

    def _platform(self) -> str:
        name = QGuiApplication.platformName()
        return "wayland" if name.startswith("wayland") else "x11" if name == "xcb" else name

    def _bridge_ready(self) -> bool:
        if self._bridge is None and self._platform() in ("wayland", "x11"):
            self._bridge = KWinBridge(self)
            self._bridge.geometryReported.connect(self._on_kwin_geometry)
        return bool(self._bridge and self._bridge.available)

    def _capabilities(self) -> dict:
        platform = self._platform()
        kwin = self._bridge_ready()
        x11 = platform == "x11"
        return {"platform": platform, "kwin": kwin, "transparent": platform in ("wayland", "x11"),
                "keepAbove": kwin or x11, "position": kwin or x11, "skipTaskbar": kwin or x11,
                "clickThrough": platform in ("wayland", "x11"), "move": platform in ("wayland", "x11"),
                # X11 shows _NET_WM_ICON; Wayland compositors with xdg-toplevel-icon (KWin 6.1+)
                # show it too, others keep the application icon
                "dynamicIcon": x11 or (platform == "wayland" and kwin)}

    capabilities = Property("QVariantMap", _capabilities, notify=changed)
    isOpen = Property(bool, lambda self: self._window is not None and self._window.isVisible(), notify=changed)  # noqa: N815

    def _screens(self) -> list[dict]:
        return [{"name": s.name(), "label": f"{s.manufacturer()} {s.model()}".strip() or s.name(),
                 "primary": s == QGuiApplication.primaryScreen()} for s in QGuiApplication.screens()]

    screens = Property("QVariantList", _screens, notify=changed)

    def _url(self) -> str:
        base = self.backend.runtimeState.get("overlayUrl", "")
        if not base:
            return ""
        return base + "?role=desktop&transparent=1" + ("" if self.settings.show_bubble else "&bubble=0")

    url = Property(str, _url, notify=changed)

    def _title(self) -> str:
        return f"{get_character(self.backend.settings.character).name} — ChatToon"

    title = Property(str, _title, notify=changed)
    characterId = Property(str, lambda self: self.backend.settings.character, notify=changed)  # noqa: N815
    characters = Property("QVariantList", lambda self: [{"id": c.id, "name": c.name, "color": c.color} for c in CHARACTERS.values()],
                          constant=True)

    # -- lifecycle ---------------------------------------------------------------------------

    def attach(self, engine) -> None:
        """Called once by the application with its QML engine."""
        self._engine = engine
        if self.backend.settings.display.mode in ("window", "both") and self.settings.window_open:
            QTimer.singleShot(400, self.show)

    def _create(self):
        component = QQmlComponent(self._engine, QUrl.fromLocalFile(str(QML)))
        d = self.settings
        width, height = (d.width, d.height) if d.size == "custom" else SIZES.get(d.size, SIZES["medium"])
        window = component.createWithInitialProperties({"controller": self, "initialWidth": max(MIN_SIZE[0], width),
                                                        "initialHeight": max(MIN_SIZE[1], height)})
        if window is None:
            log.error("character window: %s", "; ".join(e.toString() for e in component.errors()))
            return None
        # ours to keep: the QML garbage collector must never delete it while it is open
        QQmlEngine.setObjectOwnership(window, QQmlEngine.ObjectOwnership.CppOwnership)
        self._component = component
        window.setIcon(character_icon(self.backend.settings.character))
        window.widthChanged.connect(self._on_resized)
        window.heightChanged.connect(self._on_resized)
        window.visibleChanged.connect(lambda _v: self.changed.emit())
        self._apply_flags(window)
        return window

    @Slot()
    def show(self) -> None:
        if self._engine is None:
            return
        if self._window is None:
            self._window = self._create()
            if self._window is None:
                return
            self._kwin_place = True  # remembered position, or the corner the first time
            if not self._bridge_ready() and self._platform() == "x11":
                self._place_x11()
        self._window.show()
        self._update_mask()
        self._apply_kwin()
        if not self.settings.window_open:
            self.settings.window_open = True
            self.backend.settings.save()
        self.changed.emit()

    @Slot()
    def hide(self) -> None:
        """Close only the character window; ChatToon keeps running."""
        if self._window is not None:
            self._remember_x11()
            self._window.hide()
        if self.settings.window_open:
            self.settings.window_open = False
            self.backend.settings.save()
        self.changed.emit()

    @Slot()
    def toggle(self) -> None:
        self.hide() if self.isOpen else self.show()

    @Slot()
    def closed(self) -> None:
        """The window was closed from outside (taskbar, Alt+F4)."""
        self._remember_x11()
        self.settings.window_open = False
        self.backend.settings.save()
        self.changed.emit()

    def shutdown(self) -> None:
        self._remember_x11()
        if self._save.isActive():
            self._save.stop()
            self._persist()
        if self._bridge is not None:
            self._bridge.unload()
        if self._window is not None:
            self._window.destroy()
            self._window.deleteLater()
            self._window = None
        self._engine = None  # never keep the QML engine alive past the application's own reference

    # -- options ------------------------------------------------------------------------------

    def _store(self, **values) -> None:
        for k, v in values.items():
            setattr(self.settings, k, v)
        self.backend.settings.save()
        self.backend.configChanged.emit()

    @Slot(str)
    def setSize(self, size: str) -> None:  # noqa: N802
        if size not in SIZES:
            return
        width, height = SIZES[size]
        self._store(size=size, width=width, height=height)
        if self._window is not None:
            self._window.resize(width, height)

    @Slot(float)
    def scaleBy(self, factor: float) -> None:  # noqa: N802
        """Ctrl + mouse wheel on the character: grow or shrink, keeping the 2:3 shape."""
        if self._window is None or self.settings.locked:
            return
        width = int(min(1200, max(MIN_SIZE[0], self._window.width() * factor)))
        height = int(width * 1.5)
        self._window.resize(width, height)
        self._store(size="custom", width=width, height=height)

    @Slot(bool)
    def setKeepAbove(self, on: bool) -> None:  # noqa: N802
        self._store(keep_above=bool(on))
        self._refresh_flags()

    @Slot(bool)
    def setClickThrough(self, on: bool) -> None:  # noqa: N802
        self._store(click_through=bool(on))
        self._refresh_flags()

    @Slot(bool)
    def setLocked(self, on: bool) -> None:  # noqa: N802
        self._store(locked=bool(on))
        self.changed.emit()

    @Slot(bool)
    def setSkipTaskbar(self, on: bool) -> None:  # noqa: N802
        self._store(skip_taskbar=bool(on))
        self._refresh_flags()

    @Slot(bool)
    def setShowBubble(self, on: bool) -> None:  # noqa: N802
        self._store(show_bubble=bool(on))
        self.changed.emit()

    @Slot(str)
    def moveToScreen(self, name: str) -> None:  # noqa: N802
        screen = next((s for s in QGuiApplication.screens() if s.name() == name), None)
        if screen is None:
            return
        g = screen.availableGeometry()
        width, height = (self._window.width(), self._window.height()) if self._window else SIZES["medium"]
        x, y = g.x() + g.width() - width - 40, g.y() + g.height() - height - 40
        self._store(x=x, y=y, screen=name)
        if self._window is None:
            return
        if self._bridge_ready():
            self._kwin_place = True
            self._apply_kwin()
        else:
            self._window.setScreen(screen)
            self._window.setPosition(x, y)

    @Slot()
    def resetPosition(self) -> None:  # noqa: N802
        """Back to the bottom-right corner of the screen the window is on."""
        self._store(x=-1, y=-1)
        if self._window is None:
            return
        if self._bridge_ready():
            self._kwin_place = True
            self._apply_kwin()
        else:
            self._place_x11()

    @Slot()
    def raiseMain(self) -> None:  # noqa: N802
        """Bring ChatToon's main window back (Wayland may only highlight it in the taskbar)."""
        for window in QGuiApplication.topLevelWindows():
            if window is not self._window and window.title() == "ChatToon":
                window.showNormal()
                window.raise_()
                window.requestActivate()

    # -- internals -----------------------------------------------------------------------------

    def _on_config(self) -> None:
        if self.backend.settings.character != self._character:
            self._character = self.backend.settings.character
            if self._window is not None:
                self._window.setIcon(character_icon(self._character))
            self.changed.emit()  # new title: the KWin script matches the title, so it is reloaded
            QTimer.singleShot(150, self._apply_kwin)

    def _apply_flags(self, window) -> None:
        from PySide6.QtCore import Qt

        flags = Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint
        d = self.settings
        if self._platform() == "x11" and not self._bridge_ready():
            if d.keep_above:
                flags |= Qt.WindowType.WindowStaysOnTopHint
            if d.skip_taskbar:
                flags |= Qt.WindowType.Tool
        elif d.keep_above:
            flags |= Qt.WindowType.WindowStaysOnTopHint  # a hint some compositors honour
        if d.click_through:
            flags |= Qt.WindowType.WindowTransparentForInput
        window.setFlags(flags)

    def _refresh_flags(self) -> None:
        if self._window is None:
            self.changed.emit()
            return
        visible = self._window.isVisible()
        self._remember_x11()
        if visible:
            self._window.hide()  # Wayland applies new surface roles/flags on the next map
        self._apply_flags(self._window)
        if visible:
            self._kwin_place = self.settings.x >= 0
            if not self._bridge_ready() and self._platform() == "x11":
                self._place_x11()
            self._window.show()
            self._update_mask()
            self._apply_kwin()
        self.changed.emit()

    def _apply_kwin(self) -> None:
        if self._window is None or not self._window.isVisible() or not self._bridge_ready():
            return
        d = self.settings
        state = {"keepAbove": bool(d.keep_above), "skipTaskbar": bool(d.skip_taskbar),
                 "place": self._kwin_place and d.x >= 0, "x": int(d.x), "y": int(d.y),
                 "corner": self._kwin_place and d.x < 0}
        self._bridge.apply(self._title(), state)
        self._kwin_place = False

    def _on_kwin_geometry(self, g: dict) -> None:
        self._pending_geometry = dict(g)
        self._save.start()

    def _persist(self) -> None:
        g, self._pending_geometry = self._pending_geometry, {}
        if not g:
            return
        values = {"x": int(g.get("x", -1)), "y": int(g.get("y", -1)), "screen": str(g.get("output", ""))}
        if g.get("width") and g.get("height") and self.settings.size == "custom":
            values.update(width=int(g["width"]), height=int(g["height"]))
        for k, v in values.items():
            setattr(self.settings, k, v)
        self.backend.settings.save()

    def _place_x11(self) -> None:
        d = self.settings
        if self._window is None:
            return
        if d.x >= 0 and d.y >= 0:
            self._window.setPosition(d.x, d.y)
        else:
            screen = QGuiApplication.primaryScreen()
            if screen is not None:
                g = screen.availableGeometry()
                self._window.setPosition(g.x() + g.width() - self._window.width() - 40,
                                         g.y() + g.height() - self._window.height() - 40)

    def _remember_x11(self) -> None:
        if self._window is not None and self._platform() == "x11" and not self._bridge_ready() \
                and self._window.isVisible():
            self.settings.x, self.settings.y = self._window.x(), self._window.y()
            self.backend.settings.save()

    def _on_resized(self, *_args) -> None:
        self._update_mask()
        if self._window is not None and self.settings.size == "custom":
            self._pending_geometry = dict(self._pending_geometry, width=self._window.width(),
                                          height=self._window.height())
            self._save.start()

    @Slot(bool)
    def menuOpen(self, opened: bool) -> None:  # noqa: N802
        """While the menu is drawn inside the window, the whole window takes the mouse."""
        self._menu_open = bool(opened)
        self._update_mask()

    def _update_mask(self) -> None:
        """Only the character catches the mouse: clicks on the transparent space around it
        (and on the speech bubble) reach the windows below."""
        w = self._window
        if w is None:
            return
        width, height = w.width(), w.height()
        if self._menu_open:
            w.setMask(QRegion(0, 0, width, height))
            return
        # the character fills the lower ~56 % of the window (overlay.js frameDesktop)
        body = QRect(int(width * 0.1), int(height * 0.38), int(width * 0.8), int(height * 0.62))
        grip = QRect(width - 36, height - 36, 36, 36)
        w.setMask(QRegion(body, QRegion.RegionType.Ellipse).united(QRegion(grip)))

    @Slot(int, int)
    def resized(self, width: int, height: int) -> None:
        """The person resized the window with the grip."""
        self._store(size="custom", width=max(MIN_SIZE[0], width), height=max(MIN_SIZE[1], height))
