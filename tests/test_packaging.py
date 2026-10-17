import re
import shutil
import subprocess
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PKG = ROOT / "chattoon"


def _cfg():
    return tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))


def test_wheel_contains_every_runtime_file(tmp_path):
    """Build the real wheel: fnmatch-style checks miss files in subfolders (setuptools globs don't recurse)."""
    import zipfile

    if shutil.which("python") is None:
        pytest.skip("python not on PATH")
    result = subprocess.run(["python", "-m", "build", "--wheel", "--no-isolation", "--outdir", str(tmp_path)],
                            cwd=ROOT, capture_output=True, text=True)
    for leftover in ("build", "chattoon.egg-info"):
        shutil.rmtree(ROOT / leftover, ignore_errors=True)
    if result.returncode != 0 and "No module named build" in result.stderr:
        pytest.skip("python-build not installed")
    assert result.returncode == 0, result.stderr[-2000:]
    (wheel,) = tmp_path.glob("*.whl")
    names = set(zipfile.ZipFile(wheel).namelist())
    runtime = [p.relative_to(ROOT).as_posix() for d in ("gui/qml", "web", "i18n") for p in (PKG / d).rglob("*")
               if p.is_file() and p.suffix != ".ts" and "__pycache__" not in p.parts]
    missing = [f for f in runtime if f not in names]
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


def _tracked_text_files():
    """Every text file in the repository (git ls-files), or the source tree without git."""
    try:
        names = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.split()
        paths = [ROOT / n for n in names]
    except (OSError, subprocess.CalledProcessError):
        paths = [p for p in ROOT.rglob("*") if ".git" not in p.parts]
    return [p for p in paths if p.is_file() and p.suffix not in (".png", ".qm", ".whl")]


def test_no_secrets_or_shell_in_code():
    code = "\n".join(p.read_text(encoding="utf-8") for p in PKG.rglob("*.py"))
    assert "os.system" not in code and "shell=True" not in code
    everything = "\n".join(p.read_text(encoding="utf-8", errors="ignore") for p in _tracked_text_files())
    assert "dzQk" + "OLTg" not in everything  # the Rumble key exposed by an early prototype must never come back
    assert not re.search(r"AIza[0-9A-Za-z_-]{30}", everything)  # Google API keys
    assert not re.search(r"(?i)(client_secret|api_key|bearer_token|access_token)\s*[=:]\s*['\"][A-Za-z0-9_\-]{16,}", everything)


def test_appstream_metainfo_is_valid_and_installed():
    meta = ROOT / "data" / "chattoon.metainfo.xml"
    text = (ROOT / "packaging" / "arch" / "PKGBUILD").read_text(encoding="utf-8")
    assert "data/chattoon.metainfo.xml" in text and "metainfo/io.github.ruscher.ChatToon.metainfo.xml" in text
    import xml.etree.ElementTree as ET
    root = ET.parse(meta).getroot()
    assert root.find("id").text == "io.github.ruscher.ChatToon"
    assert root.find("launchable").text == "chattoon.desktop"
    assert root.find("releases/release").get("version") == _cfg()["project"]["version"]  # bumped with the app
    if shutil.which("appstreamcli"):
        r = subprocess.run(["appstreamcli", "validate", "--no-net", str(meta)], capture_output=True, text=True)
        assert r.returncode == 0, r.stdout + r.stderr
