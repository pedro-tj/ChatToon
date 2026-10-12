import asyncio
import os
import struct
import wave

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["CHATTOON_CREDENTIALS"] = "memory"  # tests never read or write the real keyring


def pytest_addoption(parser):
    parser.addoption("--run-live", action="store_true", help="use the real Ollama / TTS BigLinux / YouTube")


def pytest_configure(config):
    config.addinivalue_line("markers", "live: needs real local services or the internet (--run-live)")


def pytest_collection_modifyitems(config, items):
    if config.getoption("--run-live"):
        return
    skip = pytest.mark.skip(reason="needs --run-live")
    for item in items:
        if "live" in item.keywords:
            item.add_marker(skip)


@pytest.fixture(autouse=True)
def isolated_xdg(tmp_path, monkeypatch):
    """Never touch the user's real ~/.config or ~/.local/share."""
    for var in ("XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME"):
        monkeypatch.setenv(var, str(tmp_path / var.lower()))
    return tmp_path


def run(coro):
    return asyncio.run(coro)


def make_wav(path, seconds=1.0, rate=16000, loud_from=0.25, loud_to=0.75):
    """Silence with a loud section in the middle (for envelope tests)."""
    frames = bytearray()
    for i in range(int(seconds * rate)):
        t = i / rate
        value = 12000 if loud_from <= t <= loud_to and (i // 20) % 2 else (-12000 if loud_from <= t <= loud_to else 0)
        frames += struct.pack("<h", value)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(bytes(frames))
    return path
