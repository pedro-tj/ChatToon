"""Qt Quick application start-up."""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

from PySide6.QtCore import QLocale, QTranslator, QUrl
from PySide6.QtGui import QIcon
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtWidgets import QApplication

from .. import __version__
from .backend import Backend
from .icons import IconProvider

PACKAGE = Path(__file__).resolve().parent.parent
QML_DIR = Path(__file__).resolve().parent / "qml"
I18N_DIR = PACKAGE / "i18n"
APP_ICON = QML_DIR / "assets" / "chattoon.svg"


def webengine_available() -> bool:
    if os.environ.get("CHATTOON_NO_WEBENGINE"):
        return False
    return importlib.util.find_spec("PySide6.QtWebEngineQuick") is not None


def install_translator(app: QApplication, language: str) -> QTranslator | None:
    name = QLocale.system().name() if language in ("", "system") else language
    translator = QTranslator(app)
    for candidate in (name, name.split("_")[0]):
        if translator.load(str(I18N_DIR / f"chattoon_{candidate}.qm")):
            app.installTranslator(translator)
            return translator
    return None


def create_engine(backend: Backend, warnings: list[str] | None = None) -> QQmlApplicationEngine:
    QQuickStyle.setStyle("Basic")  # fully stylable controls; colours come from Theme.qml
    engine = QQmlApplicationEngine()

    def report(items) -> None:
        for item in items:
            if warnings is not None:
                warnings.append(item.toString())
            print(item.toString(), file=sys.stderr)

    engine.warnings.connect(report)
    engine.backend = backend  # keep the backend alive as long as the QML tree
    engine.addImageProvider("icon", IconProvider())
    ctx = engine.rootContext()
    ctx.setContextProperty("backend", backend)
    ctx.setContextProperty("webEngineAvailable", webengine_available())
    engine.load(QUrl.fromLocalFile(str(QML_DIR / "Main.qml")))
    backend.window.attach(engine)  # the character window on the desktop uses the same engine
    return engine


def run(argv: list[str] | None = None) -> int:
    if webengine_available():
        from PySide6.QtWebEngineQuick import QtWebEngineQuick
        QtWebEngineQuick.initialize()  # must happen before the application object exists
    QApplication.setApplicationName("ChatToon")
    QApplication.setApplicationVersion(__version__)
    QApplication.setOrganizationName("chattoon")
    QApplication.setDesktopFileName("chattoon")
    from ..core.credentials import install_log_redaction

    install_log_redaction()
    app = QApplication(argv or sys.argv[:1])
    app.setWindowIcon(QIcon(str(APP_ICON)))
    backend = Backend()
    install_translator(app, backend.settings.ui_language)
    engine = create_engine(backend)
    if not engine.rootObjects():
        backend.shutdown()
        return 1
    code = app.exec()
    backend.window.shutdown()  # the character window belongs to the QML engine: close it first
    del engine  # destroy QML before the backend so bindings never see a dead object
    backend.shutdown()
    return code
