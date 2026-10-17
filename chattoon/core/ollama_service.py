"""Ollama on this computer: is it installed, which service runs it, is it answering?
(docs/31-ollama-management.md)

A failed connection does not mean "not installed": the package, the systemd units (system
and user), an ``ollama serve`` started by ChatToon and the API are checked separately. A
server on another computer is never controlled — only its API is used.
"""

from __future__ import annotations

import asyncio
import os
import signal
import time
from urllib.parse import urlsplit

from . import network, system
from .config import cache_dir
from .ollama import OllamaClient, OllamaError

PACKAGE = "ollama"
ACCELERATION = ("ollama-vulkan", "ollama-cuda", "ollama-rocm")  # add-ons of the "ollama" package (Arch)
UNIT = "ollama.service"
# 11435: the Ollama bundled with Alpaca (Flatpak). Other instances explain "my models are missing".
KNOWN_PORTS = (11434, 11435)
_LOOPBACK = {"127.0.0.1", "localhost", "::1", "0.0.0.0", ""}


def host_parts(host: str) -> tuple[str, int]:
    url = host if "://" in host else f"http://{host}"
    try:
        parts = urlsplit(url)
        return (parts.hostname or "").lower(), parts.port or 11434
    except ValueError:
        return "", 11434


def is_local(host: str, runner=system.run) -> bool:
    name, _ = host_parts(host)
    if name in _LOOPBACK or name.startswith("127."):
        return True
    return network.ip_scope(name) != "" and network.has_address(name, runner)


class OllamaService:
    def __init__(self, runner=system.run):
        self.runner = runner
        self._proc: asyncio.subprocess.Process | None = None  # `ollama serve` started by ChatToon
        self._starting_until = 0.0
        self._busy = ""  # start | stop | install … (one action at a time)

    # -- facts (blocking: worker thread) -------------------------------------------------

    def facts(self) -> dict:
        r = self.runner
        binary = system.which("ollama") or ""
        package = system.installed_version(PACKAGE, r) if system.which("pacman") or r is not system.run else ""
        accel = [p for p in ACCELERATION if system.installed_version(p, r)]
        unit = system.unit_state(UNIT, False, r)
        user_unit = system.unit_state(UNIT, True, r)
        return {"binary": binary, "package": package, "acceleration": accel, "unit": unit.to_dict(),
                "userUnit": user_unit.to_dict(), "installed": bool(binary or package)}

    def install_plan(self, gpu_vendor: str) -> dict:
        """The packages that would be installed, with real sizes from the repositories."""
        from .hardware import acceleration_package

        base = system.package_info(PACKAGE, self.runner)
        options = [system.package_info(p, self.runner) for p in ACCELERATION]
        recommended = acceleration_package(gpu_vendor)
        return {"pacman": system.which("pacman") is not None, "pkexec": system.which("pkexec") is not None,
                "base": base.to_dict(), "acceleration": [o.to_dict() for o in options if o.available or o.installed],
                "recommended": recommended if any(o.name == recommended and o.available for o in options) else "",
                "gpu": gpu_vendor}

    # -- state -----------------------------------------------------------------------------

    @property
    def owns_process(self) -> bool:
        return self._proc is not None and self._proc.returncode is None

    async def status(self, host: str) -> dict:
        local = await asyncio.to_thread(is_local, host, self.runner)
        info: dict = {"host": host, "local": local, "api": False, "version": "", "error": "", "busy": self._busy}
        async with OllamaClient(host, 5) as client:
            try:
                info["version"] = await client.version()
                info["api"] = True
            except OllamaError as e:
                info["error"] = str(e)
        if not local:
            info.update(state="remote", manager="remote", canStart=False, canStop=False, canEnable=False)
            return info
        facts = await asyncio.to_thread(self.facts)
        info.update(facts)
        unit, user_unit = facts["unit"], facts["userUnit"]
        if unit["active"] == "active":
            manager = "system"
        elif user_unit["active"] == "active":
            manager = "user"
        elif self.owns_process:
            manager = "chattoon"
        else:
            manager = "external" if info["api"] else ""
        if info["api"]:
            state = "running"
            self._starting_until = 0.0
        elif self._busy == "start" or time.monotonic() < self._starting_until:
            state = "starting"
        elif not facts["installed"]:
            state = "not_installed"
        elif unit["active"] == "failed" or user_unit["active"] == "failed":
            state = "error"
        else:
            state = "stopped"
        info.update(state=state, manager=manager,
                    canStart=facts["installed"] and not info["api"],
                    canStop=info["api"] and manager in ("system", "user", "chattoon"),
                    canEnable=unit["exists"] or user_unit["exists"],
                    enabled=unit["enabled"] == "enabled" or user_unit["enabled"] == "enabled",
                    others=await self.other_instances(host))
        return info

    async def other_instances(self, host: str) -> list[dict]:
        """Other Ollama servers answering on this computer (Alpaca, a manual `ollama serve`…).
        Their models live in a different folder: the usual reason "my models are missing"."""
        name, port = host_parts(host)
        found = []
        for p in KNOWN_PORTS:
            if p == port:
                continue
            candidate = f"http://127.0.0.1:{p}"
            async with OllamaClient(candidate, 2) as client:
                try:
                    version = await client.version()
                    models = await client.list_models()
                except OllamaError:
                    continue
            found.append({"host": candidate, "version": version, "models": len(models)})
        return found

    # -- actions -----------------------------------------------------------------------

    async def _wait_api(self, host: str, seconds: float) -> bool:
        deadline = time.monotonic() + seconds
        async with OllamaClient(host, 3) as client:
            while time.monotonic() < deadline:
                try:
                    await client.version()
                    return True
                except OllamaError:
                    await asyncio.sleep(0.5)
        return False

    @staticmethod
    def _failure(result: system.CommandResult) -> str:
        text = (result.err + result.out).lower()
        if "interactive authentication required" in text:
            return "no-agent"  # no polkit agent in this session
        if "access denied" in text or "not authorized" in text or result.code in (126, 127):
            return "denied"
        return "failed"

    async def start(self, host: str) -> dict:
        """Start the local Ollama the way it is installed and wait for a real API answer."""
        if not await asyncio.to_thread(is_local, host, self.runner):
            return {"ok": False, "code": "remote"}
        if self._busy:
            return {"ok": False, "code": "busy"}
        self._busy = "start"
        try:
            facts = await asyncio.to_thread(self.facts)
            if not facts["installed"]:
                return {"ok": False, "code": "not-installed"}
            if facts["unit"]["exists"]:
                result = await system.unit_action(UNIT, "start")
                if not result.ok:
                    return {"ok": False, "code": self._failure(result), "detail": result.err.strip()[-300:]}
                how = "system"
            elif facts["userUnit"]["exists"]:
                result = await system.unit_action(UNIT, "start", user=True)
                if not result.ok:
                    return {"ok": False, "code": self._failure(result), "detail": result.err.strip()[-300:]}
                how = "user"
            else:
                if host_parts(host)[0] not in _LOOPBACK and not host_parts(host)[0].startswith("127."):
                    # ChatToon never starts an Ollama that listens on the network (docs/37)
                    return {"ok": False, "code": "not-loopback"}
                await self._spawn(host, facts["binary"])
                how = "chattoon"
            self._starting_until = time.monotonic() + 40
            if not await self._wait_api(host, 40):
                return {"ok": False, "code": "no-answer", "how": how}
            return {"ok": True, "how": how}
        finally:
            self._busy = ""

    async def _spawn(self, host: str, binary: str) -> None:
        if self.owns_process:
            return
        _, port = host_parts(host)
        env = {**os.environ, "OLLAMA_HOST": f"127.0.0.1:{port}"}  # this computer only
        log_dir = cache_dir()
        log_dir.mkdir(parents=True, exist_ok=True)
        fd = os.open(log_dir / "ollama-serve.log", os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            self._proc = await asyncio.create_subprocess_exec(
                binary or "ollama", "serve", stdin=asyncio.subprocess.DEVNULL, stdout=fd, stderr=fd, env=env,
                start_new_session=True)
        finally:
            os.close(fd)

    async def stop(self, host: str) -> dict:
        if not await asyncio.to_thread(is_local, host, self.runner):
            return {"ok": False, "code": "remote"}
        if self._busy:
            return {"ok": False, "code": "busy"}
        self._busy = "stop"
        try:
            facts = await asyncio.to_thread(self.facts)
            if facts["unit"]["active"] == "active":
                result = await system.unit_action(UNIT, "stop")
            elif facts["userUnit"]["active"] == "active":
                result = await system.unit_action(UNIT, "stop", user=True)
            elif self.owns_process:
                await self.stop_own()
                return {"ok": True}
            else:
                return {"ok": False, "code": "external"}  # started by another program: not ours to stop
            if not result.ok:
                return {"ok": False, "code": self._failure(result), "detail": result.err.strip()[-300:]}
            return {"ok": True}
        finally:
            self._busy = ""

    async def restart(self, host: str) -> dict:
        stopped = await self.stop(host)
        if not stopped["ok"] and stopped.get("code") != "external":
            return stopped
        return await self.start(host)

    async def set_enabled(self, enabled: bool) -> dict:
        """Start Ollama with the computer (system unit) or with the session (user unit)."""
        facts = await asyncio.to_thread(self.facts)
        user = not facts["unit"]["exists"] and facts["userUnit"]["exists"]
        if not facts["unit"]["exists"] and not user:
            return {"ok": False, "code": "no-unit"}
        result = await system.unit_action(UNIT, "enable" if enabled else "disable", user=user)
        return {"ok": result.ok, "code": "" if result.ok else self._failure(result), "detail": result.err.strip()[-300:]}

    async def install(self, packages: list[str], on_line=None) -> system.InstallResult:
        allowed = {PACKAGE, *ACCELERATION}
        wanted = [p for p in dict.fromkeys(packages) if p in allowed]
        if PACKAGE not in wanted:
            wanted.insert(0, PACKAGE)
        if self._busy:
            return system.InstallResult(False, "busy")
        self._busy = "install"
        try:
            return await system.install_packages(wanted, on_line)
        finally:
            self._busy = ""

    async def stop_own(self) -> None:
        """Stop the `ollama serve` ChatToon started (on request and when ChatToon closes)."""
        proc, self._proc = self._proc, None
        if proc is None or proc.returncode is not None:
            return
        for sig, wait in ((signal.SIGTERM, 5), (signal.SIGKILL, 2)):
            try:
                os.killpg(proc.pid, sig)
            except (ProcessLookupError, PermissionError):
                return
            try:
                await asyncio.wait_for(proc.wait(), wait)
                return
            except asyncio.TimeoutError:
                continue
