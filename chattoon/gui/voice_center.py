"""Voice page: engines of TTS BigLinux, their installation and Kokoro voices (docs/INTELLIGENCE.md)."""

from __future__ import annotations

import asyncio
import subprocess
import threading

from PySide6.QtCore import Property, Signal, Slot

from ..core import system, tts_manager
from ..core.tts import BigLinuxTTS
from .controller import Controller


class VoiceCenter(Controller):
    planChanged = Signal()
    installChanged = Signal()
    kokoroChanged = Signal()
    downloadChanged = Signal()

    def __init__(self, backend) -> None:
        super().__init__(backend)
        self._plan: dict = {}
        self._install: dict = {"running": False, "engine": "", "line": "", "progress": 0.0, "result": {}}
        self._kokoro: list[dict] = []
        self._download: dict = {"voice": "", "state": "idle", "progress": -1.0, "error": ""}
        self._cancel = threading.Event()

    plan = Property("QVariantMap", lambda self: self._plan, notify=planChanged)
    install = Property("QVariantMap", lambda self: self._install, notify=installChanged)
    kokoro = Property("QVariantList", lambda self: self._kokoro, notify=kokoroChanged)
    download = Property("QVariantMap", lambda self: self._download, notify=downloadChanged)
    available = Property(bool, lambda self: isinstance(self.backend.engine.tts, BigLinuxTTS), constant=True)

    @property
    def tts(self):
        return self.engine.tts

    @Slot()
    def refresh(self) -> None:
        self.backend.refreshServices()

    @Slot(str)
    def loadPlan(self, engine: str) -> None:  # noqa: N802
        if not isinstance(self.tts, BigLinuxTTS):
            return
        self._plan = {"engine": engine, "loading": True, "items": []}
        self.planChanged.emit()

        async def run() -> None:
            info = await asyncio.to_thread(tts_manager.plan, self.tts, engine, self.settings.ai.reply_language)
            self._set("_plan", dict(info, loading=False), self.planChanged)
        self.submit(run())

    @Slot(str)
    def installEngine(self, engine: str) -> None:  # noqa: N802
        """Install what loadPlan() showed (the person confirmed it in a dialog)."""
        plan = self._plan
        if self._install.get("running") or plan.get("engine") != engine or plan.get("loading"):
            return
        self._install = {"running": True, "engine": engine, "line": "", "progress": -1.0, "result": {}}
        self.installChanged.emit()

        async def run() -> None:
            if engine == tts_manager.TTS_BIGLINUX_PACKAGE:
                def line(text: str, fraction: float) -> None:
                    self._set("_install", dict(self._install, line=text[-160:], progress=fraction), self.installChanged)
                result = (await system.install_packages([tts_manager.TTS_BIGLINUX_PACKAGE], line)).to_dict()
                result["message"] = ""
            else:
                result = await asyncio.to_thread(tts_manager.install, self.tts, engine, plan.get("items", []))
            self._set("_install", {"running": False, "engine": engine, "line": "", "progress": 1.0 if result["ok"] else 0.0,
                                   "result": result}, self.installChanged)
            if result["ok"]:
                self.toast(self.tr("%1 is installed").replace("%1", tts_manager.LABELS.get(engine, "TTS BigLinux")),
                           "success")
            await self.engine.check_services()
        self.submit(run())

    @Slot()
    def loadKokoro(self) -> None:  # noqa: N802
        if not isinstance(self.tts, BigLinuxTTS):
            return

        async def run() -> None:
            self._set("_kokoro", await asyncio.to_thread(tts_manager.kokoro_voices, self.tts), self.kokoroChanged)
        self.submit(run())

    @Slot(str)
    def downloadKokoro(self, voice_id: str) -> None:  # noqa: N802
        if self._download.get("state") == "downloading" or not any(v["id"] == voice_id for v in self._kokoro):
            return
        self._cancel.clear()
        self._download = {"voice": voice_id, "state": "downloading", "progress": -1.0, "error": ""}
        self.downloadChanged.emit()

        def progress(done: int, total: int) -> None:
            self._set("_download", dict(self._download, progress=done / total if total else -1.0), self.downloadChanged)

        async def run() -> None:
            ok, error = await asyncio.to_thread(tts_manager.download_kokoro, self.tts, voice_id, progress,
                                                self._cancel.is_set)
            state = "done" if ok else "cancelled" if error == "cancelled" else "error"
            self._set("_download", {"voice": voice_id, "state": state, "progress": 1.0 if ok else -1.0,
                                    "error": "" if ok else error}, self.downloadChanged)
            if ok:
                self.toast(self.tr("Voice installed"), "success")
            self._set("_kokoro", await asyncio.to_thread(tts_manager.kokoro_voices, self.tts), self.kokoroChanged)
            await self.engine.check_services()
        self.submit(run())

    @Slot()
    def cancelDownload(self) -> None:  # noqa: N802
        self._cancel.set()

    @Slot()
    def openTtsBigLinux(self) -> None:  # noqa: N802
        """TTS BigLinux's own window has the full voice manager (every RHVoice/Piper voice)."""
        if system.which("biglinux-tts"):
            subprocess.Popen(["biglinux-tts"], start_new_session=True, stdin=subprocess.DEVNULL,  # noqa: S603
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    hasTtsApp = Property(bool, lambda self: system.which("biglinux-tts") is not None, constant=True)  # noqa: N815

    @Slot()
    def resetVoice(self) -> None:  # noqa: N802
        """Default voice, speed, pitch and volume for the selected character."""
        cs = self.settings.character_settings()
        cs.voice_id, cs.voice_rate, cs.voice_pitch = "", 0, 0
        self.settings.voice.volume = 85
        self.settings.save()
        self.backend.configChanged.emit()
        self.backend.notify(self.tr("Voice settings restored"), "success")
