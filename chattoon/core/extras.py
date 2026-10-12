"""Optional libraries that distributions do not package (today: TikTokLive).

They live in a private virtual environment, ``~/.local/share/chattoon/extras``, created
with ``--system-site-packages`` so it reuses the system Python and PySide6. Nothing is
downloaded unless the streamer runs ``chattoon extras install tiktok`` (or the commands
it prints). ChatToon itself never depends on these packages: when they are missing, the
connector that needs them reports "not installed" and everything else keeps working.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from .config import data_dir

# pinned: the TikTok connector is written and tested against this API
PACKAGES = {"tiktok": ["TikTokLive==7.0.1"]}


def venv_dir() -> Path:
    return data_dir() / "extras"


def site_packages() -> Path:
    v = sys.version_info
    return venv_dir() / "lib" / f"python{v.major}.{v.minor}" / "site-packages"


def activate() -> bool:
    """Make the extras importable (first in sys.path, so its pinned versions win)."""
    path = str(site_packages())
    if not Path(path).is_dir():
        return False
    if path not in sys.path:
        sys.path.insert(0, path)
    return True


def install_commands(name: str) -> list[list[str]]:
    venv = venv_dir()
    return [
        [sys.executable, "-m", "venv", "--system-site-packages", str(venv)],
        [str(venv / "bin" / "python"), "-m", "pip", "install", "--upgrade", *PACKAGES[name]],
    ]


def install(name: str) -> int:
    """Run the install commands (explicitly requested by the streamer from a terminal)."""
    for command in install_commands(name):
        print("$", " ".join(command), flush=True)
        result = subprocess.run(command, check=False)
        if result.returncode != 0:
            return result.returncode
    return 0
