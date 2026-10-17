"""Is the overlay really reachable through the person's own domain? (docs/SECURITY.md)

Checks one thing at a time and stops at the first failure, so the interface can say what
is wrong in plain words: the name (DNS), the port (router, CGNAT, firewall), the certificate,
the reverse proxy, ChatToon's host check, the token and the WebSocket. A filled-in form is
never taken as proof: only a real HTTPS answer and a real WebSocket hello count.

Started only by the person (button), never in the background.
"""

from __future__ import annotations

import asyncio
import ipaddress
import re
import socket
import ssl
from urllib.parse import urlsplit

import aiohttp
import aiohttp.abc

from .network import ip_scope

_HOSTNAME = re.compile(r"^(?=.{1,253}$)(?!-)[a-z0-9-]{1,63}(?<!-)(\.(?!-)[a-z0-9-]{1,63}(?<!-))+$")


def parse_base(text: str) -> tuple[str, int] | None:
    """``https://name[:port]`` → (name, port); None for anything else (http, IPs, paths…)."""
    text = (text or "").strip().rstrip("/")
    if not text:
        return None
    if "://" not in text:
        text = "https://" + text
    try:
        parts = urlsplit(text)
        port = parts.port or 443
    except ValueError:
        return None
    host = (parts.hostname or "").lower()
    if parts.scheme != "https" or parts.username or parts.password or (parts.path not in ("", "/")):
        return None
    if not _HOSTNAME.match(host) or re.fullmatch(r"[\d.]+", host):
        return None  # a domain name is needed for a certificate (not a bare IP)
    return host, port


def _step(steps: list, sid: str, ok: bool, code: str = "", detail: str = "") -> bool:
    steps.append({"id": sid, "ok": ok, "code": code, "detail": detail[:300]})
    return ok


class _Pinned(aiohttp.abc.AbstractResolver):
    """aiohttp resolves the name to the addresses the DNS step already checked."""

    def __init__(self, addresses: list[str]):
        self.addresses = addresses

    async def resolve(self, host, port=0, family=socket.AF_INET):
        return [{"hostname": host, "host": a, "port": port, "family": socket.AF_INET6 if ":" in a else socket.AF_INET,
                 "proto": 0, "flags": socket.AI_NUMERICHOST} for a in self.addresses]

    async def close(self):
        pass


async def _system_resolve(host: str, port: int) -> list[str]:
    infos = await asyncio.get_running_loop().getaddrinfo(host, port, type=socket.SOCK_STREAM)
    return sorted({i[4][0] for i in infos})


async def check(base: str, token: str, public_ip: str = "", timeout: float = 8, ssl_context=None,
                resolve=_system_resolve) -> dict:
    """Run the checks against ``https://host:port/o/<token>/``. ``public_ip`` (only if the
    person chose to look it up) lets the DNS step say whether the name points to this house.
    ``ssl_context`` and ``resolve`` exist for tests (a private CA, a fixed answer)."""
    steps: list[dict] = []
    parsed = parse_base(base)
    if not _step(steps, "format", parsed is not None, "" if parsed else "invalid-format"):
        return {"ok": False, "steps": steps}
    host, port = parsed

    # 1. DNS
    try:
        resolved = await asyncio.wait_for(resolve(host, port), timeout)
        if not resolved:
            raise OSError("no address")
    except (OSError, asyncio.TimeoutError) as e:
        _step(steps, "dns", False, "dns-failed", type(e).__name__)
        return {"ok": False, "steps": steps}
    v4 = [a for a in resolved if ":" not in a]
    if v4 and all(ip_scope(a) in ("private", "loopback", "link-local") for a in v4):
        _step(steps, "dns", False, "dns-private")  # points inside a home network: unreachable from outside
        return {"ok": False, "steps": steps}
    if public_ip and v4 and public_ip not in v4:
        _step(steps, "dns", False, "dns-mismatch")  # points to another IP (the public IP changed?)
        return {"ok": False, "steps": steps}
    cgnat = any(ip_scope(a) == "cgnat" for a in v4)
    _step(steps, "dns", True, "cgnat" if cgnat else "")
    target = (v4 or resolved)[0]  # the very address the name points to

    # 2. TCP
    try:
        _, writer = await asyncio.wait_for(asyncio.open_connection(target, port), timeout)
        writer.close()
    except asyncio.TimeoutError:
        _step(steps, "port", False, "timeout")  # firewall, missing port forward or CGNAT
        return {"ok": False, "steps": steps}
    except ConnectionRefusedError:
        _step(steps, "port", False, "refused")  # reached a computer, nothing listens on that port
        return {"ok": False, "steps": steps}
    except OSError as e:
        _step(steps, "port", False, "unreachable", type(e).__name__)
        return {"ok": False, "steps": steps}
    _step(steps, "port", True)

    # 3. TLS (system certificate authorities, hostname checked)
    ctx = ssl_context or ssl.create_default_context()
    try:
        _, writer = await asyncio.wait_for(asyncio.open_connection(target, port, ssl=ctx, server_hostname=host), timeout)
        writer.close()
    except ssl.SSLCertVerificationError as e:
        _step(steps, "tls", False, "cert-invalid", e.verify_message or "")
        return {"ok": False, "steps": steps}
    except (ssl.SSLError, OSError, asyncio.TimeoutError) as e:
        _step(steps, "tls", False, "tls-failed", type(e).__name__)  # e.g. plain HTTP on that port
        return {"ok": False, "steps": steps}
    _step(steps, "tls", True)

    # 4. HTTP through the proxy to ChatToon
    url = f"https://{host}{'' if port == 443 else f':{port}'}/o/{token}/"
    client_timeout = aiohttp.ClientTimeout(total=timeout)
    connector = aiohttp.TCPConnector(resolver=_Pinned(v4 or resolved), ssl=ctx)
    async with aiohttp.ClientSession(timeout=client_timeout, connector=connector) as http:
        try:
            async with http.get(url, allow_redirects=False) as resp:
                status, body = resp.status, (await resp.text())[:200]
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            _step(steps, "http", False, "http-failed", type(e).__name__)
            return {"ok": False, "steps": steps}
        if status == 403 and "forbidden" in body:
            ok = _step(steps, "http", False, "host-not-allowed")  # ChatToon does not know this name
        elif status == 404:
            ok = _step(steps, "http", False, "token-invalid")  # old link, or another app answers
        elif status in (502, 503, 504):
            ok = _step(steps, "http", False, "proxy-error", str(status))  # the proxy cannot reach ChatToon
        elif status != 200:
            ok = _step(steps, "http", False, "http-status", str(status))
        else:
            ok = _step(steps, "http", True)
        if not ok:
            return {"ok": False, "steps": steps}

        # 5. WebSocket (the avatar's events)
        try:
            ws_timeout = aiohttp.ClientWSTimeout(ws_close=timeout) if hasattr(aiohttp, "ClientWSTimeout") else timeout
            async with http.ws_connect(url.replace("https://", "wss://", 1) + "ws?role=probe",
                                       heartbeat=None, timeout=ws_timeout) as ws:
                msg = await asyncio.wait_for(ws.receive_json(), timeout)
            hello = isinstance(msg, dict) and msg.get("type") == "hello"
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError, TypeError) as e:
            _step(steps, "websocket", False, "ws-failed", type(e).__name__)
            return {"ok": False, "steps": steps}
        if not _step(steps, "websocket", hello, "" if hello else "ws-failed"):
            return {"ok": False, "steps": steps}
    return {"ok": True, "steps": steps}


def caddy_snippet(host: str, port: int, local_port: int) -> str:
    site = host if port == 443 else f"{host}:{port}"
    return (f"# ChatToon overlay through HTTPS. Delete this file to undo.\n{site} {{\n"
            f"\treverse_proxy 127.0.0.1:{int(local_port)}\n}}\n")


def nginx_snippet(host: str, port: int, local_port: int) -> str:
    return (f"server {{\n    listen {int(port)} ssl;\n    server_name {host};\n"
            f"    # ssl_certificate / ssl_certificate_key: your certificate (certbot…)\n"
            f"    location /o/ {{\n        proxy_pass http://127.0.0.1:{int(local_port)};\n"
            f"        proxy_http_version 1.1;\n        proxy_set_header Host $host;\n"
            f"        proxy_set_header Upgrade $http_upgrade;\n        proxy_set_header Connection \"upgrade\";\n"
            f"        proxy_read_timeout 3600s;\n    }}\n}}\n")


def is_cgnat(ip: str) -> bool:
    try:
        return ipaddress.ip_address(ip) in ipaddress.ip_network("100.64.0.0/10")
    except ValueError:
        return False
