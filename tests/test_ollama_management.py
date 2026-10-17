"""Ollama management: every model is listed and classified, the service state is told apart
(not installed / stopped / starting / running / error / remote), and a model the person chose
is never replaced silently (docs/31-ollama-management.md)."""

import asyncio

import pytest
from aiohttp import web

from chattoon.core import ollama_service, system
from chattoon.core.ollama import OllamaClient, registry_size, valid_model_name
from chattoon.core.ollama_service import OllamaService, is_local

TAGS = {"models": [
    {"name": "gemma3:4b", "size": 3_338_801_804, "modified_at": "2026-10-01T10:00:00Z",
     "details": {"family": "gemma3", "parameter_size": "4.3B", "quantization_level": "Q4_K_M", "format": "gguf"}},
    {"name": "nomic-embed-text:latest", "size": 274_302_450, "details": {"family": "nomic-bert", "parameter_size": "137M"}},
    {"name": "cruiserein/Qwen3.8-27B:latest", "size": 16_000_000_000, "details": {"family": "qwen3", "parameter_size": "27B"}},
    {"name": "hf.co/bartowski/Llama-3.2-1B-Instruct-GGUF:Q4_K_M", "size": 800_000_000, "details": {"family": "llama"}},
    {"name": "my-custom-tux:latest", "size": 2_000_000_000, "details": {"family": "llama"}},  # ollama create
    {"name": "llava:7b", "size": 4_700_000_000, "details": {"family": "llama", "families": ["llama", "clip"]}},
    {"name": "gpt-oss:120b-cloud", "size": 384, "remote_host": "https://ollama.com:443", "details": {"family": "gptoss"}},
    {"name": "broken:1b", "size": 10, "details": {}},
    {"name": "old-ollama:1b", "size": 10, "details": {"family": "llama"}},
]}
CAPS = {
    "gemma3:4b": {"capabilities": ["completion", "vision"], "model_info": {"gemma3.context_length": 131072}},
    "nomic-embed-text:latest": {"capabilities": ["embedding"]},
    "cruiserein/Qwen3.8-27B:latest": {"capabilities": ["completion", "tools", "thinking"]},
    "hf.co/bartowski/Llama-3.2-1B-Instruct-GGUF:Q4_K_M": {"capabilities": ["completion"]},
    "my-custom-tux:latest": {"capabilities": ["completion", "tools"]},
    "llava:7b": {"capabilities": ["completion", "vision"]},
    "gpt-oss:120b-cloud": {"capabilities": ["completion", "tools", "thinking"]},
    "old-ollama:1b": {},  # Ollama < 0.6 reports no capabilities
}


async def serve(handlers):
    app = web.Application()
    for method, path, fn in handlers:
        app.router.add_route(method, path, fn)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    return runner, f"http://127.0.0.1:{site._server.sockets[0].getsockname()[1]}"


def ollama_handlers():
    async def tags(request):
        return web.json_response(TAGS)

    async def show(request):
        name = (await request.json())["model"]
        if name == "broken:1b":
            return web.json_response({"error": "invalid model file"}, status=500)
        return web.json_response(CAPS[name])

    async def ps(request):
        return web.json_response({"models": [{"name": "gemma3:4b", "size": 4_000_000_000, "size_vram": 4_000_000_000}]})

    async def version(request):
        return web.json_response({"version": "0.33.3"})

    return [("GET", "/api/tags", tags), ("POST", "/api/show", show), ("GET", "/api/ps", ps), ("GET", "/api/version", version)]


def test_catalog_lists_every_model_with_the_reason_it_can_or_cannot_chat():
    async def go():
        runner, host = await serve(ollama_handlers())
        try:
            async with OllamaClient(host, 5) as c:
                return await c.catalog(), await c.running(), [m.name for m in await c.list_models()]
        finally:
            await runner.cleanup()

    catalog, loaded, legacy = asyncio.run(go())
    by = {m.name: m for m in catalog}
    assert len(catalog) == len(TAGS["models"])  # nothing disappears
    for name in ("gemma3:4b", "cruiserein/Qwen3.8-27B:latest", "hf.co/bartowski/Llama-3.2-1B-Instruct-GGUF:Q4_K_M",
                 "my-custom-tux:latest", "llava:7b", "gpt-oss:120b-cloud"):
        assert by[name].chat, name  # namespaced, imported, custom, multimodal and cloud models can chat
    assert by["nomic-embed-text:latest"].reason == "embedding" and not by["nomic-embed-text:latest"].chat
    assert by["broken:1b"].reason == "unreadable" and "invalid model file" in by["broken:1b"].error
    assert by["old-ollama:1b"].chat and by["old-ollama:1b"].capabilities_known is False
    assert by["gemma3:4b"].kind == "vision" and by["gemma3:4b"].context_length == 131072
    assert by["gemma3:4b"].quantization == "Q4_K_M" and by["gpt-oss:120b-cloud"].remote
    assert by["llava:7b"].to_dict()["capabilities"] == ["completion", "vision"]
    assert loaded == [{"name": "gemma3:4b", "vram": 4_000_000_000, "size": 4_000_000_000, "expires": ""}]
    assert "nomic-embed-text:latest" not in legacy and "gemma3:4b" in legacy


def test_engine_reports_the_catalog_and_the_loaded_models(tmp_path):
    from chattoon.core.config import Settings
    from chattoon.core.engine import ChatToonEngine
    from chattoon.core.overlay_server import OverlayServer

    from .test_engine import FakePlayer, FakeTTS

    async def go():
        runner, host = await serve(ollama_handlers())
        s = Settings()
        s.ai.host = host
        engine = ChatToonEngine(s, tts=FakeTTS(tmp_path), player=FakePlayer(), server=OverlayServer("t", 0, tmp_path))
        try:
            return await engine.check_services()
        finally:
            await engine.ollama.close()
            await runner.cleanup()

    report = asyncio.run(go())["ollama"]
    assert report["ok"] and report["version"] == "0.33.3" and report["loaded"] == ["gemma3:4b"]
    assert "my-custom-tux:latest" in report["models"] and "nomic-embed-text:latest" not in report["models"]
    assert {m["name"] for m in report["catalog"]} >= {"nomic-embed-text:latest", "broken:1b"}


@pytest.mark.parametrize("name,ok", [("gemma3:4b", True), ("user/model", True), ("hf.co/user/Repo-GGUF:Q4_K_M", True),
                                     ("../../etc/passwd", False), ("a b", False), ("x;y", False), ("", False)])
def test_model_names_are_checked_before_download(name, ok):
    assert valid_model_name(name) is ok


def test_registry_size_sums_the_manifest_layers(monkeypatch):
    async def manifest(request):
        assert request.match_info["path"] == "library/gemma3"
        return web.json_response({"layers": [{"size": 3_000_000_000}, {"size": 350_000_000}, {"size": 300}]})

    async def go():
        runner, host = await serve([("GET", "/v2/{path:.+}/manifests/{tag}", manifest)])
        monkeypatch.setattr("chattoon.core.ollama.REGISTRY", host)
        import aiohttp
        try:
            async with aiohttp.ClientSession() as http:
                return await registry_size("gemma3:4b", http), await registry_size("hf.co/a/b:c", http)
        finally:
            await runner.cleanup()

    assert asyncio.run(go()) == (3_350_000_300, 0)


# -- service states ------------------------------------------------------------------

class FakeRunner:
    def __init__(self, installed=True, unit="inactive", unit_exists=True, user_unit_exists=False):
        self.installed, self.unit, self.unit_exists, self.user_unit_exists = installed, unit, unit_exists, user_unit_exists

    def __call__(self, argv, timeout=15, env=None):
        if argv[:2] == ["pacman", "-Q"]:
            ok = self.installed and argv[-1] == "ollama"
            return system.CommandResult(0 if ok else 1, "ollama 0.33.3-1" if ok else "", "")
        if argv[0] == "systemctl":
            user = "--user" in argv
            exists = self.user_unit_exists if user else self.unit_exists
            if not exists:
                return system.CommandResult(0, "LoadState=not-found\nActiveState=inactive\n", "")
            active = "inactive" if user else self.unit
            return system.CommandResult(0, f"LoadState=loaded\nActiveState={active}\nUnitFileState=disabled\n", "")
        return system.CommandResult(1, "", "")


def status(runner, host="http://127.0.0.1:9", monkeypatch=None):
    return asyncio.run(OllamaService(runner).status(host))


@pytest.fixture
def no_binary(monkeypatch):
    real = system.which
    monkeypatch.setattr(system, "which", lambda name: None if name == "ollama" else real(name))


def test_not_installed_is_not_confused_with_a_failed_connection(no_binary):
    s = status(FakeRunner(installed=False, unit_exists=False))
    assert s["state"] == "not_installed" and s["api"] is False and not s["canStart"]


def test_installed_and_stopped_then_error(no_binary):
    s = status(FakeRunner(installed=True, unit="inactive"))
    assert s["state"] == "stopped" and s["canStart"] and s["canEnable"] and s["unit"]["exists"]
    assert status(FakeRunner(installed=True, unit="failed"))["state"] == "error"


def test_running_service_and_other_instances(no_binary, monkeypatch):
    async def go():
        runner, host = await serve(ollama_handlers())
        other_runner, other = await serve(ollama_handlers())
        monkeypatch.setattr(ollama_service, "KNOWN_PORTS", (int(other.rsplit(":", 1)[1]),))
        try:
            return await OllamaService(FakeRunner(installed=True, unit="active")).status(host)
        finally:
            await runner.cleanup()
            await other_runner.cleanup()

    s = asyncio.run(go())
    assert s["state"] == "running" and s["version"] == "0.33.3" and s["manager"] == "system" and s["canStop"]
    assert len(s["others"]) == 1 and s["others"][0]["models"] == 8  # every non-embedding model of the other one


def test_remote_server_is_used_but_never_controlled():
    assert not is_local("http://192.0.2.10:11434")
    assert is_local("http://localhost:11434") and is_local("127.0.0.1:11434")
    s = status(FakeRunner(), host="http://192.0.2.10:9")
    assert s["state"] == "remote" and not s["canStart"] and not s["canStop"]
    assert asyncio.run(OllamaService(FakeRunner()).start("http://192.0.2.10:9"))["code"] == "remote"


def test_start_uses_the_system_unit_and_waits_for_a_real_answer(no_binary, monkeypatch):
    calls = []

    async def unit_action(name, action, user=False):
        calls.append((name, action, user))
        return system.CommandResult(0)

    monkeypatch.setattr(system, "unit_action", unit_action)

    async def go():
        runner, host = await serve(ollama_handlers())
        try:
            return await OllamaService(FakeRunner(installed=True, unit="inactive")).start(host)
        finally:
            await runner.cleanup()

    assert asyncio.run(go()) == {"ok": True, "how": "system"}
    assert calls == [("ollama.service", "start", False)]


def test_start_reports_a_cancelled_password(no_binary, monkeypatch):
    async def unit_action(name, action, user=False):
        return system.CommandResult(1, "", "Failed to start ollama.service: Access denied")

    monkeypatch.setattr(system, "unit_action", unit_action)
    result = asyncio.run(OllamaService(FakeRunner(installed=True)).start("http://127.0.0.1:9"))
    assert result["code"] == "denied"


def test_an_instance_opened_elsewhere_is_not_stopped(no_binary):
    result = asyncio.run(OllamaService(FakeRunner(installed=True, unit="inactive")).stop("http://127.0.0.1:9"))
    assert result == {"ok": False, "code": "external"}


def test_install_only_accepts_ollama_packages(monkeypatch):
    seen = {}

    async def install(names, on_line=None, timeout=3600):
        seen["names"] = names
        return system.InstallResult(True, packages=names)

    monkeypatch.setattr(system, "install_packages", install)
    asyncio.run(OllamaService(FakeRunner()).install(["ollama-vulkan", "evil-package"]))
    assert seen["names"] == ["ollama", "ollama-vulkan"]


# -- the model in use ---------------------------------------------------------------

def test_a_chosen_model_is_never_replaced_silently(qapp, backend):  # noqa: F811 - shared fixture
    from .test_gui import pump

    backend.setConfig("ai.model", "my-model:8b")  # chosen by the person, not installed in this Ollama
    backend.engine.bus.emit("services", {"ollama": {"ok": True, "models": ["gemma3:4b"]}, "tts": {"ok": True, "voices": []}})
    assert pump(2, lambda: any("my-model:8b" in m for m, _ in backend.toasts))
    assert backend.config["ai"]["model"] == "my-model:8b"
    assert backend.ai.selectModel("not-installed:1b") is False  # unknown: refused
    backend._services = {"ollama": {"ok": True, "models": ["gemma3:4b"],
                                    "catalog": [{"name": "nomic-embed-text:latest", "chat": False}]}}
    assert backend.ai.selectModel("nomic-embed-text:latest") is False
    assert backend.ai.selectModel("gemma3:4b") is True and backend.config["ai"]["model"] == "gemma3:4b"


from .test_gui import backend, qapp  # noqa: E402,F401 - shared fixtures


def test_chattoon_never_starts_an_ollama_listening_on_the_network(no_binary, monkeypatch):
    monkeypatch.setattr(ollama_service, "is_local", lambda host, runner=None: True)  # a LAN IP of this computer
    monkeypatch.setattr(system, "which", lambda name: "/usr/bin/ollama" if name == "ollama" else None)
    service = OllamaService(FakeRunner(installed=True, unit_exists=False))
    assert asyncio.run(service.start("http://192.168.0.235:11434")) == {"ok": False, "code": "not-loopback"}
    assert service._proc is None
