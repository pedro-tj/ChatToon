import fnmatch
import re
import shutil
import subprocess
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKG = ROOT / "chattoon"


def _cfg():
    return tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))


def test_package_data_covers_runtime_files():
    patterns = _cfg()["tool"]["setuptools"]["package-data"]["chattoon"]
    runtime = [p.relative_to(PKG).as_posix() for d in ("gui/qml", "web", "i18n") for p in (PKG / d).rglob("*")
               if p.is_file() and p.suffix != ".ts" and "__pycache__" not in p.parts]
    missing = [f for f in runtime if not any(fnmatch.fnmatch(f, pat) for pat in patterns)]
    assert runtime and missing == []


def test_pkgbuild_matches_project():
    text = (ROOT / "packaging" / "arch" / "PKGBUILD").read_text(encoding="utf-8")
    values = dict(re.findall(r"^(\w+)=(.*)$", text, re.MULTILINE))
    assert values["pkgver"] == _cfg()["project"]["version"]
    for dep in ("python", "pyside6", "python-aiohttp", "qt6-webengine"):
        assert f"'{dep}'" in values["depends"]
    assert "tts-biglinux" in text and "'tts-biglinux'" not in values["depends"]  # optional, BigLinux repo
    for path in ("data/chattoon.desktop", "data/chattoon.svg"):
        assert path in text and (ROOT / path).exists()


def test_desktop_file_and_icon():
    from PySide6.QtSvg import QSvgRenderer

    assert QSvgRenderer(str(ROOT / "data" / "chattoon.svg")).isValid()
    assert (ROOT / "data" / "chattoon.svg").read_bytes() == (PKG / "gui" / "qml" / "assets" / "chattoon.svg").read_bytes()
    if shutil.which("desktop-file-validate"):
        r = subprocess.run(["desktop-file-validate", str(ROOT / "data" / "chattoon.desktop")], capture_output=True, text=True)
        assert r.returncode == 0, r.stdout + r.stderr


def test_vendored_three_is_intact_and_licensed():
    folder = PKG / "web" / "vendor" / "three"
    assert "MIT" in (folder / "LICENSE").read_text()
    for line in (folder / "SHA256SUMS").read_text().splitlines():
        digest, name = line.split()
        import hashlib
        assert hashlib.sha256((folder / name).read_bytes()).hexdigest() == digest, name


def test_no_secrets_or_shell_in_code():
    code = "\n".join(p.read_text(encoding="utf-8") for p in PKG.rglob("*.py"))
    assert "os.system" not in code and "shell=True" not in code
    everything = code + "\n".join(p.read_text(encoding="utf-8", errors="ignore") for p in (ROOT / "legacy").glob("*"))
    assert "dzQkOLTg" not in everything  # the exposed Rumble key must never come back
    assert not re.search(r"AIza[0-9A-Za-z_-]{30}", everything)  # Google API keys
