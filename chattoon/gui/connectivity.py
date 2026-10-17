"""Where the OBS is: this computer, the local network or the internet
(docs/33-obs-network-access.md, docs/34-remote-access-privacy.md)."""

from __future__ import annotations

import asyncio
import secrets

import aiohttp
from PySide6.QtCore import Property, Signal, Slot

from ..core import network, remote_check, system
from ..core.overlay_server import public_base, valid_lan_address
from .controller import Controller


class Connectivity(Controller):
    networkChanged = Signal()
    lanTestChanged = Signal()
    publicIpChanged = Signal()
    remoteChanged = Signal()
    proxyChanged = Signal()

    def __init__(self, backend) -> None:
        super().__init__(backend)
        self._network: dict = {"addresses": [], "firewall": {}, "ipv6": False, "loading": False}
        self._lan_test: dict = {"state": "idle", "code": ""}
        self._public_ip: dict = {"known": False, "value": "", "cgnat": False, "state": "idle"}
        self._remote: dict = {"state": "idle", "ok": False, "steps": []}
        self._proxy: dict = {}

    network = Property("QVariantMap", lambda self: self._network, notify=networkChanged)
    lanTest = Property("QVariantMap", lambda self: self._lan_test, notify=lanTestChanged)  # noqa: N815
    publicIp = Property("QVariantMap", lambda self: self._public_ip, notify=publicIpChanged)  # noqa: N815
    remote = Property("QVariantMap", lambda self: self._remote, notify=remoteChanged)
    proxy = Property("QVariantMap", lambda self: self._proxy, notify=proxyChanged)

    def _set(self, attr: str, value, signal) -> None:
        def apply() -> None:
            setattr(self, attr, value)
            signal.emit()
        self.later(apply)

    # -- local network ---------------------------------------------------------------------

    @Slot()
    def refresh(self) -> None:
        self._network = dict(self._network, loading=True)
        self.networkChanged.emit()

        def read() -> dict:
            return {"addresses": network.lan_candidates(), "firewall": network.firewall(),
                    "ipv6": bool(network.global_ipv6()), "loading": False}

        async def run() -> None:
            self._set("_network", await asyncio.to_thread(read), self.networkChanged)
        self.submit(run())

    def _address(self, ip: str) -> dict | None:
        return next((a for a in self._network.get("addresses", []) if a["ip"] == ip), None)

    @Slot(bool, str)
    def setLan(self, enabled: bool, address: str) -> None:  # noqa: N802
        """Turn the local-network address on (after the person's consent) or off."""
        address = address.strip()
        if enabled and (not valid_lan_address(address) or self._address(address) is None):
            self.backend.notify(self.tr("Choose an address of this computer on your home network."), "error")
            return
        o = self.settings.overlay
        o.lan_enabled, o.lan_address = bool(enabled), address if enabled else o.lan_address
        self.settings.save()
        self.backend.configChanged.emit()
        self._lan_test = {"state": "idle", "code": ""}
        self.lanTestChanged.emit()
        self.submit(self.engine.apply_network())

    @Slot()
    def testLan(self) -> None:  # noqa: N802
        url = self.engine.server.lan_url
        if not url:
            return
        self._lan_test = {"state": "testing", "code": ""}
        self.lanTestChanged.emit()

        async def run() -> None:
            try:
                async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5)) as http:
                    async with http.get(url) as resp:
                        code = "" if resp.status == 200 else f"http-{resp.status}"
            except (aiohttp.ClientError, asyncio.TimeoutError, OSError) as e:
                code = type(e).__name__
            self._set("_lan_test", {"state": "ok" if not code else "failed", "code": code}, self.lanTestChanged)
        self.submit(run())

    @Slot(bool)
    def allowFirewall(self, remove: bool = False) -> None:  # noqa: N802
        """Let only the home network reach the overlay port (asks for the password)."""
        fw = self._network.get("firewall", {})
        kind = "ufw" if fw.get("ufw") else "firewalld" if fw.get("firewalld") else ""
        found = self._address(self.settings.overlay.lan_address)
        if not kind or found is None or not self.engine.server.port:
            return

        async def run() -> None:
            result = await network.apply_firewall(kind, self.engine.server.port, found["network"], remove)
            if result.ok:
                self.toast(self.tr("Firewall rule removed") if remove else self.tr("Firewall allows your home network"),
                           "success")
            else:
                self.toast(self.tr("The firewall was not changed."), "error")
        self.submit(run())

    @Slot(result="QVariantList")
    def firewallCommand(self) -> list:  # noqa: N802
        fw = self._network.get("firewall", {})
        kind = "ufw" if fw.get("ufw") else "firewalld" if fw.get("firewalld") else ""
        found = self._address(self.settings.overlay.lan_address)
        if not kind or not found:
            return []
        return ["sudo", *network.firewall_command(kind, self.engine.server.port or self.settings.overlay.port,
                                                  found["network"])]

    # -- token -------------------------------------------------------------------------------

    @Slot()
    def rotateToken(self) -> None:  # noqa: N802
        token = secrets.token_urlsafe(12)
        self.settings.overlay.token = token
        self.settings.save()
        self.backend.remember_secret(token)
        self.submit(self.engine.rotate_token(token))
        self.backend.notify(self.tr("New address created. Paste it again in OBS: the old one no longer works."),
                            "success")

    # -- internet ----------------------------------------------------------------------------

    @Slot()
    def lookupPublicIp(self) -> None:  # noqa: N802
        """Ask api.ipify.org for the public IP — only after the consent dialog."""
        self._public_ip = dict(self._public_ip, state="loading")
        self.publicIpChanged.emit()

        async def run() -> None:
            try:
                async with aiohttp.ClientSession() as http:
                    ip = await network.public_ip(http)
                self.backend.remember_secret(ip)
                info = {"known": True, "value": ip, "cgnat": remote_check.is_cgnat(ip), "state": "idle",
                        "scope": network.ip_scope(ip)}
            except (aiohttp.ClientError, asyncio.TimeoutError, OSError, ValueError):
                info = {"known": False, "value": "", "cgnat": False, "state": "error"}
            self._set("_public_ip", info, self.publicIpChanged)
        self.submit(run())

    @Slot()
    def forgetPublicIp(self) -> None:  # noqa: N802
        self._public_ip = {"known": False, "value": "", "cgnat": False, "state": "idle"}
        self.publicIpChanged.emit()

    @Slot(str, result=str)
    def normalizeAddress(self, text: str) -> str:  # noqa: N802
        return public_base(text)

    @Slot(str, result=bool)
    def validDomain(self, text: str) -> bool:  # noqa: N802
        return remote_check.parse_base(text) is not None

    @Slot()
    def checkRemote(self) -> None:  # noqa: N802
        base = self.settings.overlay.public_address
        self._remote = {"state": "checking", "ok": False, "steps": []}
        self.remoteChanged.emit()

        async def run() -> None:
            result = await remote_check.check(base, self.settings.overlay.token,
                                              self._public_ip.get("value", "") if self._public_ip.get("known") else "")
            self._set("_remote", dict(result, state="done"), self.remoteChanged)
        self.submit(run())

    @Slot()
    def loadProxy(self) -> None:  # noqa: N802
        def read() -> dict:
            info = {}
            for name in ("caddy", "nginx", "cloudflared", "tailscale"):
                info[name] = {"installed": system.which(name) is not None,
                              "active": system.is_active(f"{name}.service") if name in ("caddy", "nginx", "tailscaled") else False}
            info["tailscale"]["active"] = system.is_active("tailscaled.service")
            parsed = remote_check.parse_base(self.settings.overlay.public_address)
            host, port = parsed if parsed else ("example.org", 8443)
            local = self.engine.server.port or self.settings.overlay.port
            info["caddySnippet"] = remote_check.caddy_snippet(host, port, local)
            info["nginxSnippet"] = remote_check.nginx_snippet(host, port, local)
            info["localPort"] = local
            return info

        async def run() -> None:
            self._set("_proxy", await asyncio.to_thread(read), self.proxyChanged)
        self.submit(run())
