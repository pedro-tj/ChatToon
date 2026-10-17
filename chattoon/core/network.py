"""This computer's network, seen from the inside (docs/33-obs-network-access.md).

Nothing here contacts the internet: addresses come from ``ip -j addr`` and the kernel's
/sys tree; ``ip route get`` only asks the local routing table which interface would be used.
The public IP is a separate, consented query (:func:`public_ip`).
"""

from __future__ import annotations

import ipaddress
import json
import re
from dataclasses import dataclass
from pathlib import Path

from . import system

SYS_NET = Path("/sys/class/net")
_VIRTUAL = re.compile(r"^(docker|br-|veth|virbr|vmnet|vboxnet|lxc|lxd|podman|cni|flannel|cali|kube|vnet|incus)")
_VPN = re.compile(r"^(tun|tap|wg|tailscale|zt|ppp|nordlynx|proton|mullvad|ipsec|utun|vpn|cscotun|gpd)")
# what ChatToon may ask about the public IP, and only after the person agreed
PUBLIC_IP_SERVICE = "https://api.ipify.org"


@dataclass
class Address:
    ip: str
    prefix: int
    interface: str
    kind: str  # ethernet | wifi | vpn | virtual | loopback | other
    scope: str  # private | cgnat | public | link-local | loopback
    default: bool = False  # the interface the default route uses

    @property
    def network(self) -> str:
        return str(ipaddress.ip_interface(f"{self.ip}/{self.prefix}").network)

    def to_dict(self) -> dict:
        return {"ip": self.ip, "prefix": self.prefix, "interface": self.interface, "kind": self.kind,
                "scope": self.scope, "default": self.default, "network": self.network,
                "lan": self.kind in ("ethernet", "wifi", "other") and self.scope in ("private", "link-local")}


def ip_scope(ip: str) -> str:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return ""
    if addr.is_loopback:
        return "loopback"
    if addr.is_link_local:
        return "link-local"
    if addr.version == 4 and addr in ipaddress.ip_network("100.64.0.0/10"):
        return "cgnat"  # carrier-grade NAT (and Tailscale)
    if addr.is_private:
        return "private"
    return "public" if addr.is_global else "private"


def interface_kind(name: str, sys_net: Path = SYS_NET) -> str:
    base = sys_net / name
    if name == "lo":
        return "loopback"
    if (base / "wireless").exists() or (base / "phy80211").exists():
        return "wifi"
    if _VPN.match(name):
        return "vpn"
    if _VIRTUAL.match(name) or (base / "bridge").exists():
        return "virtual"
    try:
        kind = (base / "type").read_text().strip()
    except OSError:
        kind = ""
    if kind == "65534":  # no hardware address: a tunnel
        return "vpn"
    if (base / "device").exists():
        return "ethernet"
    return "other" if kind == "1" else "virtual"


def _default_interface(runner=system.run) -> str:
    result = runner(["ip", "-j", "route", "get", "1.1.1.1"], 5)  # a routing-table lookup, nothing is sent
    try:
        return json.loads(result.out)[0].get("dev", "") if result.ok else ""
    except (ValueError, IndexError, AttributeError):
        return ""


def addresses(runner=system.run, sys_net: Path = SYS_NET, family: int = 4) -> list[Address]:
    """Every IPv4 (or IPv6) address of this computer, the default-route interface first,
    physical networks before VPNs and virtual bridges (Docker, libvirt…)."""
    result = runner(["ip", "-j", f"-{family}", "addr", "show"], 5)
    try:
        data = json.loads(result.out) if result.ok else []
    except ValueError:
        data = []
    default = _default_interface(runner)
    out: list[Address] = []
    for iface in data if isinstance(data, list) else []:
        name = str(iface.get("ifname", ""))
        if not name or "UP" not in iface.get("flags", ["UP"]):
            continue
        kind = interface_kind(name, sys_net)
        for a in iface.get("addr_info", []):
            ip = str(a.get("local", ""))
            if family == 6 and a.get("scope") != "global":
                continue
            scope = ip_scope(ip)
            if not scope:
                continue
            out.append(Address(ip, int(a.get("prefixlen", 32)), name, kind, scope, name == default))
    order = {"ethernet": 0, "wifi": 0, "other": 1, "vpn": 2, "virtual": 3, "loopback": 4}
    return sorted(out, key=lambda a: (not a.default, order.get(a.kind, 5), a.interface))


def lan_candidates(runner=system.run, sys_net: Path = SYS_NET) -> list[dict]:
    """Addresses another computer of the same network could use, best first."""
    return [a.to_dict() for a in addresses(runner, sys_net) if a.scope in ("private", "link-local", "cgnat")]


def has_address(ip: str, runner=system.run) -> bool:
    return any(a.ip == ip for a in addresses(runner))


def global_ipv6(runner=system.run, sys_net: Path = SYS_NET) -> list[str]:
    return [a.ip for a in addresses(runner, sys_net, family=6)
            if a.scope == "public" and a.kind in ("ethernet", "wifi", "other")]


# -- firewall -------------------------------------------------------------------------

def firewall(runner=system.run) -> dict:
    """Which firewall is on. Changing it is the person's decision (see firewall_command)."""
    ufw = system.is_active("ufw.service", runner=runner)
    firewalld = system.is_active("firewalld.service", runner=runner)
    return {"active": ufw or firewalld, "ufw": ufw, "firewalld": firewalld}


def firewall_command(kind: str, port: int, network: str) -> list[str]:
    """The exact command that lets only ``network`` reach the overlay port (shown to the person
    and, after their consent, run through pkexec)."""
    port = int(port)
    net = str(ipaddress.ip_network(network, strict=False))
    if kind == "ufw":
        return ["ufw", "allow", "from", net, "to", "any", "port", str(port), "proto", "tcp", "comment", "ChatToon overlay"]
    if kind == "firewalld":
        rule = f'rule family="ipv4" source address="{net}" port port="{port}" protocol="tcp" accept'
        return ["firewall-cmd", "--permanent", f"--add-rich-rule={rule}"]
    return []


def firewall_remove_command(kind: str, port: int, network: str) -> list[str]:
    cmd = firewall_command(kind, port, network)
    if kind == "ufw" and cmd:
        return ["ufw", "delete", *cmd[1:]]
    if kind == "firewalld" and cmd:
        return [cmd[0], cmd[1], cmd[2].replace("--add-rich-rule", "--remove-rich-rule")]
    return []


async def apply_firewall(kind: str, port: int, network: str, remove: bool = False) -> system.CommandResult:
    import asyncio

    cmd = firewall_remove_command(kind, port, network) if remove else firewall_command(kind, port, network)
    if not cmd:
        return system.CommandResult(2, "", "no firewall")
    result = await asyncio.to_thread(system.run, ["pkexec", *cmd], 120)
    if result.ok and kind == "firewalld":
        await asyncio.to_thread(system.run, ["pkexec", "firewall-cmd", "--reload"], 60)
    return result


# -- public IP (consent required) ---------------------------------------------------------

async def public_ip(session, timeout: float = 8) -> str:
    """Ask one service for this connection's public IPv4. Call ONLY after the person agreed:
    the service sees the request. The answer is never saved, logged or shown unmasked."""
    import aiohttp

    async with session.get(PUBLIC_IP_SERVICE, timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
        text = (await resp.text()).strip()
    addr = ipaddress.ip_address(text)  # ValueError for anything that is not an address
    if addr.version != 4:
        raise ValueError("not IPv4")
    return str(addr)
