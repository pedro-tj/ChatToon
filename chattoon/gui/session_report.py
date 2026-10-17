"""Start button: check what is ready, start only if nothing essential is missing, then show
a short report of what the character really does (docs/ARCHITECTURE.md)."""

from __future__ import annotations

from PySide6.QtCore import Property, Signal, Slot

from ..core import readiness
from ..core.tts import TTSError
from .controller import Controller


class SessionReport(Controller):
    reportChanged = Signal()
    openRequested = Signal()  # the interface shows the report dialog

    def __init__(self, backend) -> None:
        super().__init__(backend)
        self._report: dict = {"state": "none"}

    report = Property("QVariantMap", lambda self: self._report, notify=reportChanged)

    @Slot()
    def check(self) -> None:
        """Health check: the same report, without going live."""
        self._run(start=False)

    @Slot()
    @Slot(bool)
    def startLive(self, show: bool = True) -> None:  # noqa: N802
        self._run(start=True, show=show)

    def _run(self, start: bool, show: bool = True) -> None:
        self._report = dict(self._report, state="checking", start=start)
        self.reportChanged.emit()
        if start and show:
            self.openRequested.emit()
        b = self.backend
        window_open = b.window.isOpen

        async def run() -> None:
            services = await self.engine.check_services()
            service = await b.ai.service.status(self.settings.ai.host)
            b.ai._set("_status", service, b.ai.serviceChanged)
            try:
                voice = self.engine.voice_for()
            except TTSError:
                voice = None
            report = readiness.build(self.settings, services, service, list(b._sources), self.engine.server.counts(),
                                     voice, window_open)
            report["start"] = start
            if start and report["ok"]:
                await self.engine.start()
                report["state"] = "running" if self.engine.state == "running" else "blocked"
            elif start and not show:
                self.later(self.openRequested.emit)  # something essential is missing: say what
            elif not start:
                report["state"] = "checked" if report["ok"] else "blocked"
            self._set("_report", report, self.reportChanged)
            # proof: the model answers (only when nothing blocks) and the voice speaks — silently
            proof = await self.engine.verify(ai=report["ok"]) if report["ok"] or report["voice"]["status"] == "ok" else None
            if proof is None:
                return
            report = dict(report)
            if report["ok"]:
                report["ai"] = dict(report["ai"], responded=proof["ai"], seconds=proof["aiSeconds"])
                if proof["ai"] is False:
                    report["ai"].update(status="error", code="model-failed")
            report["voice"] = dict(report["voice"], verified=proof["voice"], seconds=proof["voiceSeconds"])
            if proof["voice"] is False:
                report["voice"].update(status="warn", code="voice-failed")
                report["warnings"] = [*report["warnings"], "voice-failed"]
            self._set("_report", report, self.reportChanged)
        self.submit(run())
