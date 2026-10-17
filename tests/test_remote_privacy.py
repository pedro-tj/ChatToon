"""Internet access check, privacy masking and the start report (docs/34, docs/35).

The remote check runs against a real HTTPS server on this computer, with a certificate from a
throw-away authority; the "public" address is faked so nothing leaves the machine."""

import asyncio
import json
import shutil
import ssl
import subprocess

import pytest
from aiohttp import web

from chattoon.core import readiness, remote_check
from chattoon.core.config import Settings, SourceConfig
from chattoon.core.overlay_server import OverlayServer
from chattoon.core.privacy import mask_url_token, scrub

HOST = "overlay.example.org"


# -- parsing ----------------------------------------------------------------------------

@pytest.mark.parametrize("text,expected", [
    ("https://overlay.example.org:8443", ("overlay.example.org", 8443)),
    ("overlay.example.org", ("overlay.example.org", 443)),
    ("http://overlay.example.org", None), ("https://203.0.113.5", None), ("https://user:pw@x.org", None),
    ("https://x.org/o/token/", None), ("", None), ("https://bad_name.org", None),
])
def test_parse_base(text, expected):
    assert remote_check.parse_base(text) == expected


def run_check(**kw):
    return asyncio.run(remote_check.check(kw.pop("base", f"https://{HOST}:9"), "tok", **kw))


def test_dns_failures():
    async def nxdomain(host, port):
        raise OSError("Name or service not known")

    async def private(host, port):
        return ["192.168.0.5"]

    async def other(host, port):
        return ["8.8.4.4"]

    assert run_check(base="nope")["steps"][-1]["code"] == "invalid-format"
    assert run_check(resolve=nxdomain)["steps"][-1]["code"] == "dns-failed"
    assert run_check(resolve=private)["steps"][-1]["code"] == "dns-private"
    assert run_check(resolve=other, public_ip="177.10.2.3")["steps"][-1]["code"] == "dns-mismatch"


@pytest.fixture
def public_loopback(monkeypatch):
    """127.0.0.1 plays the part of a public IP."""
    real = remote_check.ip_scope
    monkeypatch.setattr(remote_check, "ip_scope", lambda ip: "public" if ip == "127.0.0.1" else real(ip))

    async def resolve(host, port):
        return ["127.0.0.1"]
    return resolve


def free_port():
    import socket
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def test_closed_port(public_loopback):
    result = run_check(base=f"https://{HOST}:{free_port()}", resolve=public_loopback)
    assert not result["ok"] and result["steps"][-1] == {"id": "port", "ok": False, "code": "refused", "detail": ""}


@pytest.fixture(scope="module")
def certs(tmp_path_factory):
    if not shutil.which("openssl"):
        pytest.skip("openssl not installed")
    d = tmp_path_factory.mktemp("tls")
    subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-keyout", str(d / "key.pem"),
                    "-out", str(d / "cert.pem"), "-days", "1", "-subj", f"/CN={HOST}",
                    "-addext", f"subjectAltName=DNS:{HOST}"], check=True, capture_output=True)
    return d


async def tls_overlay(web_dir, certs, public=True, status=None):
    """An OverlayServer reached through HTTPS (the TLS site stands in for Caddy)."""
    server = OverlayServer("tok", 0, web_dir)
    await server.start()
    ctx = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
    ctx.load_cert_chain(certs / "cert.pem", certs / "key.pem")
    if status:
        async def fail(request):
            return web.Response(status=status, text="bad gateway")
        app = web.Application()
        app.router.add_get("/{tail:.*}", fail)
        runner = web.AppRunner(app)
        await runner.setup()
    else:
        runner = server._runner
    site = web.TCPSite(runner, "127.0.0.1", 0, ssl_context=ctx)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]
    if public:
        server.set_public_address(f"https://{HOST}:{port}")
    return server, port, runner


def client_ctx(certs):
    ctx = ssl.create_default_context()
    ctx.load_verify_locations(certs / "cert.pem")
    return ctx


@pytest.fixture
def web_dir(tmp_path):
    (tmp_path / "overlay").mkdir()
    (tmp_path / "overlay" / "index.html").write_text("<html>overlay</html>")
    return tmp_path


def test_the_whole_path_works_through_https(web_dir, certs, public_loopback):
    async def go():
        server, port, _ = await tls_overlay(web_dir, certs)
        try:
            return await remote_check.check(f"https://{HOST}:{port}", "tok", ssl_context=client_ctx(certs),
                                            resolve=public_loopback)
        finally:
            await server.stop()

    result = asyncio.run(go())
    assert result["ok"], result
    assert [s["id"] for s in result["steps"]] == ["format", "dns", "port", "tls", "http", "websocket"]


def test_untrusted_certificate(web_dir, certs, public_loopback):
    async def go():
        server, port, _ = await tls_overlay(web_dir, certs)
        try:
            return await remote_check.check(f"https://{HOST}:{port}", "tok", resolve=public_loopback)  # system CAs
        finally:
            await server.stop()

    assert asyncio.run(go())["steps"][-1]["code"] == "cert-invalid"


def test_unknown_host_wrong_token_and_proxy_error(web_dir, certs, public_loopback):
    async def go():
        out = {}
        server, port, _ = await tls_overlay(web_dir, certs, public=False)  # ChatToon does not know the name
        out["host"] = await remote_check.check(f"https://{HOST}:{port}", "tok", ssl_context=client_ctx(certs),
                                               resolve=public_loopback)
        server.set_public_address(f"https://{HOST}:{port}")
        out["token"] = await remote_check.check(f"https://{HOST}:{port}", "old-token", ssl_context=client_ctx(certs),
                                                resolve=public_loopback)
        await server.stop()
        server, port, runner = await tls_overlay(web_dir, certs, status=502)
        out["proxy"] = await remote_check.check(f"https://{HOST}:{port}", "tok", ssl_context=client_ctx(certs),
                                                resolve=public_loopback)
        await runner.cleanup()
        await server.stop()
        return out

    out = asyncio.run(go())
    assert out["host"]["steps"][-1]["code"] == "host-not-allowed"
    assert out["token"]["steps"][-1]["code"] == "token-invalid"
    assert out["proxy"]["steps"][-1]["code"] == "proxy-error"


def test_plain_http_on_the_https_port(public_loopback):
    async def go():
        async def hello(request):
            return web.Response(text="hi")
        app = web.Application()
        app.router.add_get("/", hello)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "127.0.0.1", 0)
        await site.start()
        port = site._server.sockets[0].getsockname()[1]
        try:
            return await remote_check.check(f"https://{HOST}:{port}", "tok", resolve=public_loopback)
        finally:
            await runner.cleanup()

    assert asyncio.run(go())["steps"][-1]["code"] == "tls-failed"


def test_proxy_snippets_forward_websockets_to_the_real_port():
    caddy = remote_check.caddy_snippet(HOST, 8443, 8766)
    assert f"{HOST}:8443 {{" in caddy and "reverse_proxy 127.0.0.1:8766" in caddy
    nginx = remote_check.nginx_snippet(HOST, 8443, 8766)
    assert "proxy_set_header Upgrade $http_upgrade" in nginx and "127.0.0.1:8766" in nginx
    assert remote_check.is_cgnat("100.70.1.2") and not remote_check.is_cgnat("203.0.113.1")


# -- privacy ---------------------------------------------------------------------------

def test_tokens_and_public_ips_are_always_masked():
    text = "OBS at http://127.0.0.1:8765/o/5kt9GMi9yv-NFTAo/ via 177.10.2.3 and 192.168.0.235 at 12:30"
    calm = scrub(text, live=False)
    assert "5kt9GMi9yv" not in calm and "177.10.2.3" not in calm
    assert "127.0.0.1" in calm and "192.168.0.235" in calm and "12:30" in calm
    live = scrub(text, live=True)
    assert "192.168.0.235" not in live and "127.0.0.1" in live
    assert scrub("key abcdefgh123 here", ("abcdefgh123",), live=False) == "key •••••• here"
    assert mask_url_token("https://x.org/o/abcdef123/ws") == "https://x.org/o/••••••/ws"
    assert "2804:14c" not in scrub("ipv6 2804:14c:6527:435e:75ba:4f74:4c74:e8c7", live=False)


def test_toasts_never_show_the_token(qapp, backend):  # noqa: F811 - shared fixture
    from .test_gui import pump

    token = backend.settings.overlay.token
    backend.engine.bus.emit("error", {"source": "x", "message": f"failed http://127.0.0.1:1/o/{token}/"})
    assert pump(2, lambda: backend.toasts)
    assert all(token not in m for m, _ in backend.toasts)
    backend.copyText(f"http://127.0.0.1:8765/o/{token}/")
    assert "secret" in backend.toasts[-1][0]


# -- start report ----------------------------------------------------------------------

def services(ok=True, models=("gemma3:4b",), catalog=(), tts=True):
    return {"ollama": {"ok": ok, "models": list(models), "catalog": list(catalog), "version": "0.33.3"},
            "tts": {"ok": tts, "voices": [{"id": "v"}] if tts else []}}


class Voice:
    backend, name = "piper", "Faber"


def test_report_when_everything_is_ready():
    s = Settings(mode="auto")
    s.ai.model = "gemma3:4b"
    sources = [SourceConfig(platform="twitch", target="ana").__dict__ | {"status": {"state": "idle"}}]
    r = readiness.build(s, services(), {"state": "running", "local": True}, sources, {"obs": 1}, Voice())
    assert r["ok"] and r["blocking"] == [] and r["state"] == "starting"
    assert r["ai"]["code"] == "ready" and r["voice"]["engine"] == "piper" and r["platforms"]["items"][0]["platform"] == "twitch"
    on = {i["id"]: i["on"] for i in r["interactions"]}
    assert on["answer"] and on["platforms"] and on["voice"] and on["read_message"] and not on["spontaneous"]
    assert s.overlay.token not in json.dumps(r)  # no credentials in the report


@pytest.mark.parametrize("svc,service,model,code", [
    (services(ok=False), {"state": "not_installed"}, "gemma3:4b", "ollama-not-installed"),
    (services(ok=False), {"state": "stopped"}, "gemma3:4b", "ollama-stopped"),
    (services(ok=False), {"state": "remote"}, "gemma3:4b", "ollama-remote-down"),
    (services(models=()), {"state": "running"}, "", "no-chat-model"),
    (services(), {"state": "running"}, "", "no-model"),
    (services(), {"state": "running"}, "llama3.1:8b", "model-missing"),
    (services(catalog=[{"name": "nomic-embed-text:latest", "chat": False}]), {"state": "running"},
     "nomic-embed-text:latest", "model-incompatible"),
])
def test_missing_ai_blocks_the_start(svc, service, model, code):
    s = Settings()
    s.ai.model = model
    r = readiness.build(s, svc, service, [], {}, Voice())
    assert not r["ok"] and r["ai"]["code"] == code and code in r["blocking"] and r["state"] == "blocked"


def test_platform_required_outside_demo_and_optional_extras_only_warn():
    s = Settings(mode="assisted")
    s.ai.model = "gemma3:4b"
    s.voice.enabled = False
    s.display.mode = "both"
    r = readiness.build(s, services(tts=False), {"state": "running"}, [], {"obs": 0}, None, window_open=False)
    assert r["blocking"] == ["no-platform"]
    assert r["voice"]["code"] == "muted" and "muted" in r["warnings"]
    assert r["display"]["code"] == "window-closed"
    assert readiness.build(Settings(mode="demo"), services(), {}, [], {}, Voice())["platforms"]["code"] == "demo"


from .test_gui import backend, qapp  # noqa: E402,F401 - shared fixtures
