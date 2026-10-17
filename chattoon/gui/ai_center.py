"""The AI page as a small control centre: Ollama's service and the models (docs/ARCHITECTURE.md)."""

from __future__ import annotations

import asyncio
import subprocess
import time

import aiohttp
from PySide6.QtCore import Property, QUrl, Signal, Slot
from PySide6.QtGui import QDesktopServices

from ..core import hardware, system
from ..core.ollama import SUGGESTED, OllamaClient, OllamaError, registry_size, valid_model_name
from ..core.ollama_service import OllamaService
from .controller import Controller

_IDLE_PULL = {"model": "", "state": "idle", "status": "", "progress": -1.0, "completed": 0, "total": 0,
              "speed": 0.0, "error": ""}


class OllamaCenter(Controller):
    serviceChanged = Signal()
    planChanged = Signal()
    installChanged = Signal()
    pullChanged = Signal()
    hardwareChanged = Signal()
    sizeReady = Signal(str, float)  # model, bytes (0 = unknown)

    def __init__(self, backend, service: OllamaService | None = None) -> None:
        super().__init__(backend)
        self.service = service or OllamaService()
        self._status: dict = {"state": "checking"}
        self._plan: dict = {}
        self._install: dict = {"running": False, "line": "", "progress": 0.0, "result": {}}
        self._pull: dict = dict(_IDLE_PULL)
        self._pull_future = None
        self._hardware: dict = {}
        self._sizes: dict[str, int] = {}

    # -- properties ----------------------------------------------------------------------

    status = Property("QVariantMap", lambda self: self._status, notify=serviceChanged)
    plan = Property("QVariantMap", lambda self: self._plan, notify=planChanged)
    install = Property("QVariantMap", lambda self: self._install, notify=installChanged)
    pull = Property("QVariantMap", lambda self: self._pull, notify=pullChanged)
    hardware = Property("QVariantMap", lambda self: self._hardware, notify=hardwareChanged)

    def _suggestions(self) -> list[dict]:
        hw = self._hardware or {}
        return [dict(s, fit=hardware.fits(s["bytes"], hw) if hw else "unknown") for s in SUGGESTED]

    suggestions = Property("QVariantList", _suggestions, notify=hardwareChanged)

    # -- state ---------------------------------------------------------------------------

    @Slot()
    def refresh(self) -> None:
        """Check the service again (and the models, through the engine)."""
        self._status = dict(self._status, checking=True)
        self.serviceChanged.emit()

        async def run() -> None:
            status = await self.service.status(self.settings.ai.host)
            self._set("_status", status, self.serviceChanged)
            await self.engine.check_services()
        self.submit(run())
        if not self._hardware:
            self.submit(self._load_hardware())

    async def _load_hardware(self) -> None:
        self._set("_hardware", await asyncio.to_thread(hardware.summary), self.hardwareChanged)

    @Slot()
    def loadPlan(self) -> None:  # noqa: N802
        async def run() -> None:
            if not self._hardware:
                await self._load_hardware()
            vendor = (self._hardware or {}).get("gpuVendor", "") or (await asyncio.to_thread(hardware.summary))["gpuVendor"]
            info = await asyncio.to_thread(self.service.install_plan, vendor)
            info["distro"] = await asyncio.to_thread(system.distro)
            self._set("_plan", info, self.planChanged)
        self.submit(run())

    # -- install and service ---------------------------------------------------------------

    @Slot("QVariantList")
    def installOllama(self, packages) -> None:  # noqa: N802
        if self._install.get("running"):
            return
        names = [str(p) for p in (packages or [])]
        self._install = {"running": True, "line": "", "progress": 0.0, "result": {}, "packages": names}
        self.installChanged.emit()

        def line(text: str, fraction: float) -> None:
            self._set("_install", dict(self._install, line=text[-160:], progress=fraction), self.installChanged)

        async def run() -> None:
            result = await self.service.install(names, line)
            self._set("_install", {"running": False, "line": "", "progress": 1.0 if result.ok else 0.0,
                                   "result": result.to_dict(), "packages": names}, self.installChanged)
            if result.ok:
                self.toast(self.tr("Ollama installed"), "success")
            status = await self.service.status(self.settings.ai.host)
            self._set("_status", status, self.serviceChanged)
        self.submit(run())

    def _action(self, coro_fn, success: str) -> None:
        self._status = dict(self._status, busy="action")
        self.serviceChanged.emit()

        async def run() -> None:
            result = await coro_fn()
            if result.get("ok"):
                self.toast(success, "success")
            else:
                self.toast(self.service_error(result.get("code", "")), "error")
            self._set("_status", await self.service.status(self.settings.ai.host), self.serviceChanged)
            await self.engine.check_services()
        self.submit(run())

    def service_error(self, code: str) -> str:
        return {
            "denied": self.tr("The administrator password was not confirmed."),
            "no-agent": self.tr("No password dialog is available in this session (polkit agent)."),
            "no-answer": self.tr("Ollama started but did not answer in 40 seconds. Try again or restart it."),
            "external": self.tr("This Ollama was opened by another program (Alpaca, a terminal…). Close it there."),
            "remote": self.tr("Ollama runs on another computer: control it there."),
            "not-installed": self.tr("Ollama is not installed."),
            "no-unit": self.tr("This Ollama has no system service to start with the computer."),
            "busy": self.tr("Wait for the current action to finish."),
            "not-loopback": self.tr("ChatToon only starts Ollama for this computer (127.0.0.1). Use the address http://127.0.0.1:11434."),
        }.get(code, self.tr("The action failed."))

    @Slot()
    def start(self) -> None:
        host = self.settings.ai.host
        self._action(lambda: self.service.start(host), self.tr("Ollama is running"))

    @Slot()
    def stop(self) -> None:
        host = self.settings.ai.host
        self._action(lambda: self.service.stop(host), self.tr("Ollama stopped"))

    @Slot()
    def restart(self) -> None:
        host = self.settings.ai.host
        self._action(lambda: self.service.restart(host), self.tr("Ollama restarted"))

    @Slot(bool)
    def setAutostart(self, enabled: bool) -> None:  # noqa: N802
        self._action(lambda: self.service.set_enabled(enabled),
                     self.tr("Ollama starts with the computer") if enabled else self.tr("Ollama no longer starts by itself"))

    @Slot(str)
    def useHost(self, host: str) -> None:  # noqa: N802
        """Point ChatToon to another Ollama (e.g. the one found on another port)."""
        self.backend.setConfig("ai.host", host.strip())
        self.refresh()

    @Slot(str)
    def openStore(self, package: str) -> None:  # noqa: N802
        """Open the system's own software centre on the package (BigLinux: Pamac)."""
        if not system.SAFE_PACKAGE.match(package):
            return
        store = system.distro()["store"]
        argv = ["pamac-manager", f"--details={package}"] if store == "pamac-manager" else [store] if store else []
        if argv:
            subprocess.Popen(argv, start_new_session=True, stdin=subprocess.DEVNULL,  # noqa: S603 - fixed argv
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            QDesktopServices.openUrl(QUrl(f"https://archlinux.org/packages/?q={package}"))

    # -- models --------------------------------------------------------------------------

    def _catalog(self) -> dict:
        return {m["name"]: m for m in (self.backend.services.get("ollama", {}).get("catalog") or [])}

    @Slot(str, result=bool)
    def selectModel(self, name: str) -> bool:  # noqa: N802
        info = self._catalog().get(name)
        chat = self.backend.services.get("ollama", {}).get("models") or []
        if (info is not None and not info.get("chat")) or (info is None and name not in chat):
            self.backend.notify(self.tr("This model cannot answer the chat."), "error")
            return False
        self.backend.setConfig("ai.model", name)
        self.backend.notify(self.tr("%1 is now in use").replace("%1", name), "success")
        return True

    @Slot(str)
    def downloadSize(self, model: str) -> None:  # noqa: N802
        if model in self._sizes:
            self.sizeReady.emit(model, float(self._sizes[model]))
            return

        async def run() -> None:
            async with aiohttp.ClientSession() as http:
                size = await registry_size(model, http)
            self._sizes[model] = size
            self.later(lambda: self.sizeReady.emit(model, float(size)))
        self.submit(run())

    @Slot(str)
    def pullModel(self, model: str) -> None:  # noqa: N802
        model = model.strip()
        if not valid_model_name(model):
            self.backend.notify(self.tr("This is not a valid model name."), "error")
            return
        if self._pull.get("state") == "downloading":
            return
        layers: dict[str, tuple[int, int]] = {}
        meter = {"t": time.monotonic(), "bytes": 0, "speed": 0.0, "last": 0.0}
        self._pull = dict(_IDLE_PULL, model=model, state="downloading", status="pulling manifest")
        self.pullChanged.emit()

        def event(e: dict) -> None:
            digest = str(e.get("digest") or "")
            if digest and e.get("total"):
                layers[digest] = (int(e.get("completed") or 0), int(e["total"]))
            done = sum(c for c, _ in layers.values())
            total = sum(t for _, t in layers.values())
            now = time.monotonic()
            if now - meter["t"] >= 0.5:
                rate = (done - meter["bytes"]) / (now - meter["t"])
                meter["speed"] = rate if not meter["speed"] else meter["speed"] * 0.6 + rate * 0.4
                meter["t"], meter["bytes"] = now, done
            if now - meter["last"] < 0.15 and e.get("status") != "success":
                return  # at most ~7 updates a second reach the interface
            meter["last"] = now
            state = dict(self._pull, status=str(e.get("status") or ""), completed=done, total=total,
                         progress=done / total if total else -1.0, speed=max(0.0, meter["speed"]))
            self._set("_pull", state, self.pullChanged)

        async def run() -> None:
            try:
                async with OllamaClient(self.settings.ai.host, 30) as client:
                    await client.pull(model, on_event=event)
                final = dict(self._pull, state="done", status="success", progress=1.0)
                self._set("_pull", final, self.pullChanged)
                self.toast(self.tr("%1 downloaded and installed").replace("%1", model), "success")
                await self.engine.check_services()
                if not self.settings.ai.model:
                    self.later(lambda: self.selectModel(model))
            except asyncio.CancelledError:
                gone = dict(self._pull, state="cancelled", progress=-1.0)
                self._set("_pull", gone, self.pullChanged)
                raise
            except (OllamaError, aiohttp.ClientError, OSError, ValueError) as e:
                failed = dict(self._pull, state="error", error=str(e)[:200], progress=-1.0)
                self._set("_pull", failed, self.pullChanged)
                self.toast(self.tr("The download failed: %1").replace("%1", str(e)[:120]), "error")

        self._pull_future = self.submit(run())

    @Slot()
    def cancelPull(self) -> None:  # noqa: N802
        if self._pull_future and not self._pull_future.done():
            self._pull_future.cancel()  # closes the stream; Ollama keeps the parts to resume later

    async def shutdown(self) -> None:
        await self.service.stop_own()
