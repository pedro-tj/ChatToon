"""The operating system, safely: commands, distribution, packages and services.

Rules (docs/37-security-performance.md):
* argv lists only — never a shell, never text from the chat or the network in a command;
* package and unit names are checked against strict patterns before they reach a command;
* read-only queries run as the user (``pacman -Q/-Si``, ``systemctl show``);
* changes ask for consent first and then for the administrator password through polkit:
  ``pkexec pacman -S --needed`` (never ``-Sy``: refreshing the databases without upgrading
  is a partial upgrade) and ``systemctl start|stop|enable`` (systemd asks polkit itself);
* pacman runs with ``LC_ALL=C`` so its output can be parsed; the interface translates.

Everything here blocks: call it from a worker thread or use the async helpers.
"""

from __future__ import annotations

import asyncio
import os
import re
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

C_ENV = {**os.environ, "LC_ALL": "C", "LANG": "C"}
PACMAN_LOCK = Path("/var/lib/pacman/db.lck")
SAFE_PACKAGE = re.compile(r"^[A-Za-z0-9@_+][A-Za-z0-9@._+-]{0,120}$")
SAFE_UNIT = re.compile(r"^[A-Za-z0-9@_][A-Za-z0-9@._-]{0,120}\.service$")
UNIT_ACTIONS = ("start", "stop", "restart", "enable", "disable")


@dataclass
class CommandResult:
    code: int
    out: str = ""
    err: str = ""

    @property
    def ok(self) -> bool:
        return self.code == 0


def which(name: str) -> str | None:
    return shutil.which(name)


def run(argv: list[str], timeout: float = 15, env: dict | None = None) -> CommandResult:
    """Run a program (argv list, no shell) and capture its output."""
    if not argv or (which(argv[0]) is None and not os.path.isfile(argv[0])):
        return CommandResult(127, "", f"{argv[0] if argv else '?'}: not found")
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=timeout, env=env or C_ENV,
                              stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        return CommandResult(124, "", "timeout")
    except OSError as e:
        return CommandResult(126, "", str(e))
    return CommandResult(proc.returncode, proc.stdout or "", proc.stderr or "")


# -- distribution -----------------------------------------------------------------

def os_release(path: Path = Path("/etc/os-release")) -> dict[str, str]:
    data: dict[str, str] = {}
    try:
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            key, sep, value = line.partition("=")
            if sep and key.strip():
                data[key.strip()] = value.strip().strip('"').strip("'")
    except OSError:
        pass
    return data


def distro(path: Path = Path("/etc/os-release")) -> dict:
    """Which family the system belongs to and whether ChatToon can install packages on it."""
    info = os_release(path)
    ids = {info.get("ID", "").lower(), *info.get("ID_LIKE", "").lower().split()}
    family = ("arch" if ids & {"arch", "manjaro", "biglinux", "endeavouros", "cachyos", "garuda"}
              else "debian" if ids & {"debian", "ubuntu"} else "fedora" if ids & {"fedora", "rhel"}
              else "suse" if any("suse" in i for i in ids) else "other")
    return {"id": info.get("ID", ""), "name": info.get("PRETTY_NAME") or info.get("NAME", ""), "family": family,
            "pacman": which("pacman") is not None, "pkexec": which("pkexec") is not None,
            "store": next((s for s in ("pamac-manager", "big-store", "plasma-discover") if which(s)), "")}


# -- packages (pacman) --------------------------------------------------------------

@dataclass
class PackageInfo:
    name: str
    available: bool = False  # in the configured repositories
    installed: str = ""  # installed version ("" = not installed)
    repository: str = ""
    version: str = ""  # version in the repositories
    download_size: str = ""  # as pacman prints it ("16.61 MiB")
    installed_size: str = ""
    depends: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"name": self.name, "available": self.available, "installed": self.installed,
                "repository": self.repository, "version": self.version, "downloadSize": self.download_size,
                "installedSize": self.installed_size}


def _fields(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in text.splitlines():
        key, sep, value = line.partition(":")
        if sep and key and not key.startswith(" "):
            out.setdefault(key.strip(), value.strip())
    return out


def installed_version(name: str, runner=run) -> str:
    if not SAFE_PACKAGE.match(name):
        return ""
    result = runner(["pacman", "-Q", "--", name], 10)
    if not result.ok:
        return ""
    parts = result.out.split()
    return parts[1] if len(parts) >= 2 else ""


def package_info(name: str, runner=run) -> PackageInfo:
    """Installed? Available in the repositories, at which size? (no root, read-only)"""
    info = PackageInfo(name)
    if not SAFE_PACKAGE.match(name) or which("pacman") is None and runner is run:
        return info
    info.installed = installed_version(name, runner)
    result = runner(["pacman", "-Si", "--", name], 20)
    if result.ok:
        f = _fields(result.out)
        info.available = True
        info.repository = f.get("Repository", "")
        info.version = f.get("Version", "")
        info.download_size = f.get("Download Size", "")
        info.installed_size = f.get("Installed Size", "")
        info.depends = [d for d in f.get("Depends On", "").split() if d != "None"]
    return info


def pick_spelling(names: list[str], runner=run) -> str:
    """The first of several spellings that is installed, else the first that is available
    (BigLinux stable has ``piper-voices-pt-br``, testing ``piper-voices-pt-BR``)."""
    for n in names:
        if installed_version(n, runner):
            return n
    for n in names:
        if package_info(n, runner).available:
            return n
    return ""


@dataclass
class InstallResult:
    ok: bool
    code: str = ""  # cancelled | not-found | locked | network | conflict | disk | no-pkexec | timeout | failed
    detail: str = ""  # pacman's own error lines (technical, untranslated)
    packages: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"ok": self.ok, "code": self.code, "detail": self.detail, "packages": self.packages}


def explain_failure(returncode: int, output: str, packages: list[str]) -> InstallResult:
    """Turn pacman/pkexec output into a code the interface explains in plain words."""
    errors = [ln.strip() for ln in output.splitlines() if ln.strip().lower().startswith("error:")]
    detail = "\n".join(errors) or "\n".join(output.strip().splitlines()[-5:])
    text = output.lower()
    if returncode in (126, 127) and not errors:
        code = "cancelled"  # the password dialog was dismissed
    elif "target not found" in text:
        code = "not-found"
    elif "unable to lock database" in text:
        code = "locked"
    elif any(s in text for s in ("failed retrieving file", "could not resolve host", "failed to synchronize")):
        code = "network"
    elif "conflicting files" in text or "are in conflict" in text:
        code = "conflict"
    elif "not enough free disk space" in text:
        code = "disk"
    else:
        code = "failed"
    return InstallResult(False, code, detail[-1500:], packages)


_STEP = re.compile(r"\((\d+)/(\d+)\)\s+(checking|loading|installing|upgrading|reinstalling|downloading)?", re.I)


async def install_packages(packages: list[str], on_line: Callable[[str, float], None] | None = None,
                           timeout: float = 3600) -> InstallResult:
    """``pkexec pacman -S --needed --noconfirm`` the packages, reporting each output line and
    a rough fraction (pacman's ``(2/5) installing …`` steps). Cannot be cancelled once the
    password was given: the process runs as root."""
    packages = [p for p in packages if SAFE_PACKAGE.match(p)]
    if not packages:
        return InstallResult(False, "failed", "nothing to install")
    if which("pkexec") is None:
        return InstallResult(False, "no-pkexec", "", packages)
    if PACMAN_LOCK.exists():
        return InstallResult(False, "locked", str(PACMAN_LOCK), packages)
    argv = ["pkexec", "env", "LC_ALL=C", "LANG=C", "pacman", "-S", "--noconfirm", "--needed", "--", *packages]
    try:
        proc = await asyncio.create_subprocess_exec(*argv, stdin=asyncio.subprocess.DEVNULL,
                                                    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
    except OSError as e:
        return InstallResult(False, "no-pkexec", str(e), packages)
    lines: list[str] = []
    fraction = 0.0

    async def read() -> None:
        nonlocal fraction
        assert proc.stdout is not None
        async for raw in proc.stdout:
            line = raw.decode("utf-8", "replace").rstrip()
            if not line:
                continue
            lines.append(line)
            del lines[:-400]
            step = _STEP.search(line)
            if step:
                done, total = int(step.group(1)), max(1, int(step.group(2)))
                stage = (step.group(3) or "").lower()
                # downloading/checking take the first half, installing the second
                base = 0.5 if stage in ("installing", "upgrading", "reinstalling", "loading") else 0.0
                fraction = max(fraction, min(0.99, base + 0.5 * done / total))
            if on_line:
                on_line(line, fraction)

    try:
        await asyncio.wait_for(asyncio.gather(read(), proc.wait()), timeout)
    except asyncio.TimeoutError:
        return InstallResult(False, "timeout", "", packages)
    if proc.returncode == 0:
        return InstallResult(True, packages=packages)
    return explain_failure(proc.returncode or 1, "\n".join(lines), packages)


# -- services (systemd) ---------------------------------------------------------------

@dataclass
class UnitState:
    name: str
    scope: str  # system | user
    load: str = "not-found"  # loaded | not-found | masked …
    active: str = "inactive"  # active | inactive | failed | activating | deactivating
    sub: str = ""
    enabled: str = ""  # enabled | disabled | static | …

    @property
    def exists(self) -> bool:
        return self.load == "loaded"

    def to_dict(self) -> dict:
        return {"name": self.name, "scope": self.scope, "exists": self.exists, "active": self.active,
                "enabled": self.enabled}


def unit_state(name: str, user: bool = False, runner=run) -> UnitState:
    state = UnitState(name, "user" if user else "system")
    if not SAFE_UNIT.match(name):
        return state
    argv = ["systemctl", *(["--user"] if user else []), "show", "--no-pager",
            "-p", "LoadState", "-p", "ActiveState", "-p", "SubState", "-p", "UnitFileState", "--", name]
    result = runner(argv, 10)
    if not result.ok:
        return state
    values = dict(line.split("=", 1) for line in result.out.splitlines() if "=" in line)
    state.load = values.get("LoadState", "not-found")
    state.active = values.get("ActiveState", "inactive")
    state.sub = values.get("SubState", "")
    state.enabled = values.get("UnitFileState", "")
    return state


async def unit_action(name: str, action: str, user: bool = False) -> CommandResult:
    """start/stop/restart/enable/disable a unit. A system unit makes systemd ask polkit for
    the administrator password (the desktop's own dialog); a user unit needs no password."""
    if not SAFE_UNIT.match(name) or action not in UNIT_ACTIONS:
        return CommandResult(2, "", "invalid unit or action")
    argv = ["systemctl", *(["--user"] if user else []), action, "--", name]
    return await asyncio.to_thread(run, argv, 120)


def is_active(name: str, user: bool = False, runner=run) -> bool:
    return unit_state(name, user, runner).active == "active"
