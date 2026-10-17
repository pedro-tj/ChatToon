"""Operating system helpers: packages, services, distribution, hardware and the local network
(docs/ARCHITECTURE.md, docs/ARCHITECTURE.md). Commands are faked: nothing is installed, started or queried for real."""

import asyncio
import json

import pytest
from aiohttp import web

from chattoon.core import hardware, network, system


class Runner:
    """Fake command runner: argv prefix -> CommandResult."""

    def __init__(self, table):
        self.table, self.calls = table, []

    def __call__(self, argv, timeout=15, env=None):
        self.calls.append(argv)
        for prefix, result in self.table.items():
            if tuple(argv[:len(prefix)]) == prefix:
                return result if isinstance(result, system.CommandResult) else system.CommandResult(*result)
        return system.CommandResult(1, "", "unknown")


SI_OLLAMA = """Repository      : extra
Name            : ollama
Version         : 0.33.3-1
Depends On      : glibc  gcc-libs
Download Size   : 16.61 MiB
Installed Size  : 66.65 MiB
"""


def test_package_info_reads_pacman_in_c_locale():
    r = Runner({("pacman", "-Q"): (1, "", "error: package 'ollama' was not found"), ("pacman", "-Si"): (0, SI_OLLAMA, "")})
    info = system.package_info("ollama", r)
    assert info.available and not info.installed
    assert (info.repository, info.version, info.download_size) == ("extra", "0.33.3-1", "16.61 MiB")
    assert info.depends == ["glibc", "gcc-libs"]
    assert system.package_info("ollama; rm -rf /", r).available is False  # never reaches a command
    assert all(c[0] == "pacman" for c in r.calls) and len(r.calls) == 2


@pytest.mark.parametrize("code,output,expected", [
    (126, "", "cancelled"),
    (1, "error: target not found: ollama-x", "not-found"),
    (1, "error: failed to init transaction (unable to lock database)", "locked"),
    (1, "error: failed retrieving file 'x' from mirror : Could not resolve host", "network"),
    (1, "error: failed to commit transaction (conflicting files)", "conflict"),
    (1, "error: Partition / too full: 1 blocks needed\nerror: not enough free disk space", "disk"),
    (1, "error: something else", "failed"),
])
def test_install_failures_become_plain_codes(code, output, expected):
    result = system.explain_failure(code, output, ["ollama"])
    assert not result.ok and result.code == expected


def test_install_needs_pkexec_and_valid_names(monkeypatch):
    assert asyncio.run(system.install_packages(["bad name"])).code == "failed"
    monkeypatch.setattr(system, "which", lambda name: None)
    assert asyncio.run(system.install_packages(["ollama"])).code == "no-pkexec"


def test_install_streams_progress_and_never_refreshes_databases(monkeypatch, tmp_path):
    seen = {}

    async def fake_exec(*argv, **kw):
        seen["argv"] = argv

        class Proc:
            returncode = 0

            def __init__(self):
                self.stdout = self._lines()

            async def _lines(self):
                for line in (b"resolving dependencies...\n", b"(1/2) checking keys in keyring\n",
                             b"(2/2) installing ollama\n"):
                    yield line

            async def wait(self):
                return 0
        return Proc()

    monkeypatch.setattr(system, "which", lambda name: "/usr/bin/" + name)
    monkeypatch.setattr(system, "PACMAN_LOCK", tmp_path / "db.lck")
    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
    lines = []
    result = asyncio.run(system.install_packages(["ollama", "ollama-vulkan"], lambda t, f: lines.append((t, f))))
    assert result.ok
    argv = seen["argv"]
    assert argv[:2] == ("pkexec", "env") and "-S" in argv and "--needed" in argv and "-Sy" not in argv
    assert argv[-2:] == ("ollama", "ollama-vulkan") and "--" in argv
    assert lines[-1][1] >= 0.9 and lines[1][1] < 0.5  # checking: first half · installing: second half


def test_install_refuses_while_pacman_is_busy(monkeypatch, tmp_path):
    lock = tmp_path / "db.lck"
    lock.write_text("")
    monkeypatch.setattr(system, "which", lambda name: "/usr/bin/" + name)
    monkeypatch.setattr(system, "PACMAN_LOCK", lock)
    assert asyncio.run(system.install_packages(["ollama"])).code == "locked"


def test_unit_state_and_actions_are_validated():
    r = Runner({("systemctl", "show"): (0, "LoadState=loaded\nActiveState=failed\nSubState=failed\nUnitFileState=enabled\n", ""),
                ("systemctl", "--user", "show"): (0, "LoadState=not-found\nActiveState=inactive\n", "")})
    s = system.unit_state("ollama.service", runner=r)
    assert s.exists and s.active == "failed" and s.enabled == "enabled" and s.scope == "system"
    assert not system.unit_state("ollama.service", user=True, runner=r).exists
    assert asyncio.run(system.unit_action("ollama.service", "mask")).code == 2  # not an allowed action
    assert asyncio.run(system.unit_action("x;y.service", "start")).code == 2


def test_distro_family(tmp_path):
    f = tmp_path / "os-release"
    f.write_text('NAME="BigLinux"\nID="biglinux"\nID_LIKE=arch\nPRETTY_NAME="BigLinux based on Manjaro Linux"\n')
    d = system.distro(f)
    assert d["family"] == "arch" and d["name"].startswith("BigLinux")
    f.write_text("ID=ubuntu\nID_LIKE=debian\n")
    assert system.distro(f)["family"] == "debian"


# -- hardware -------------------------------------------------------------------------

def test_hardware_reads_proc_and_sys(tmp_path):
    proc = tmp_path / "proc"
    proc.mkdir()
    (proc / "cpuinfo").write_text("processor : 0\nmodel name\t: AMD Ryzen 7 5700G with Radeon Graphics\n")
    (proc / "meminfo").write_text("MemTotal:       16384000 kB\nMemAvailable:    8192000 kB\n")
    assert hardware.cpu(proc)["name"].startswith("AMD Ryzen")
    assert hardware.memory(proc)["total"] == 16384000 * 1024
    sysroot = tmp_path / "sys"
    for card, vendor, vram in (("card0", "0x1002", "17095983104"), ("card1", "0x8086", "")):
        dev = sysroot / "class" / "drm" / card / "device"
        dev.mkdir(parents=True)
        (dev / "vendor").write_text(vendor)
        (dev / "device").write_text(card)
        if vram:
            (dev / "mem_info_vram_total").write_text(vram)
    gpus = hardware.gpus(sysroot)
    assert gpus[0]["vendor"] == "amd" and gpus[0]["vram"] == 17095983104 and gpus[1]["vendor"] == "intel"
    assert hardware.acceleration_package("amd") == "ollama-vulkan"
    assert hardware.acceleration_package("nvidia") == "ollama-cuda" and hardware.acceleration_package("") == ""


def test_model_fit_is_only_a_hint():
    hw = {"vram": 8 * 2**30, "memory": {"total": 16 * 2**30}}
    assert hardware.fits(3_000_000_000, hw) == "good"
    assert hardware.fits(9_000_000_000, hw) == "heavy"
    assert hardware.fits(6_000_000_000, {"vram": 0, "memory": {"total": 32 * 2**30}}) == "ok"
    assert hardware.fits(0, hw) == "unknown"


# -- network ---------------------------------------------------------------------------

IP_ADDR = [
    {"ifname": "lo", "flags": ["LOOPBACK", "UP"], "addr_info": [{"local": "127.0.0.1", "prefixlen": 8}]},
    {"ifname": "docker0", "flags": ["UP"], "addr_info": [{"local": "172.17.0.1", "prefixlen": 16}]},
    {"ifname": "tailscale0", "flags": ["UP"], "addr_info": [{"local": "100.100.184.97", "prefixlen": 32}]},
    {"ifname": "wlan0", "flags": ["UP"], "addr_info": [{"local": "10.0.0.5", "prefixlen": 24}]},
    {"ifname": "enp7s0", "flags": ["UP"], "addr_info": [{"local": "192.168.0.235", "prefixlen": 24}]},
    {"ifname": "eth9", "flags": ["DOWN"], "addr_info": [{"local": "192.168.9.9", "prefixlen": 24}]},
]


@pytest.fixture
def fake_net(tmp_path):
    sys_net = tmp_path / "net"
    for name, extra in (("lo", []), ("docker0", ["bridge"]), ("tailscale0", []), ("wlan0", ["wireless", "device"]),
                        ("enp7s0", ["device"])):
        (sys_net / name).mkdir(parents=True)
        (sys_net / name / "type").write_text("65534\n" if name == "tailscale0" else "1\n")
        for e in extra:
            (sys_net / name / e).mkdir()
    runner = Runner({("ip", "-j", "-4", "addr"): (0, json.dumps(IP_ADDR), ""),
                     ("ip", "-j", "route", "get"): (0, json.dumps([{"dev": "enp7s0", "prefsrc": "192.168.0.235"}]), "")})
    return runner, sys_net


def test_addresses_are_classified_and_ranked(fake_net):
    runner, sys_net = fake_net
    found = network.addresses(runner, sys_net)
    kinds = {a.interface: (a.kind, a.scope) for a in found}
    assert kinds["enp7s0"] == ("ethernet", "private") and kinds["wlan0"] == ("wifi", "private")
    assert kinds["docker0"] == ("virtual", "private") and kinds["tailscale0"] == ("vpn", "cgnat")
    assert "eth9" not in kinds  # interface down
    assert found[0].interface == "enp7s0" and found[0].default  # the default route first
    lan = network.lan_candidates(runner, sys_net)
    assert [a["ip"] for a in lan if a["lan"]] == ["192.168.0.235", "10.0.0.5"]  # VPN and Docker are not "home network"
    assert lan[0]["network"] == "192.168.0.0/24"


@pytest.mark.parametrize("ip,scope", [("127.0.0.1", "loopback"), ("192.168.1.2", "private"), ("10.1.2.3", "private"),
                                      ("100.64.0.1", "cgnat"), ("169.254.3.4", "link-local"), ("8.8.8.8", "public"),
                                      ("not an ip", "")])
def test_ip_scope(ip, scope):
    assert network.ip_scope(ip) == scope


def test_firewall_commands_allow_only_the_home_network():
    ufw = network.firewall_command("ufw", 8765, "192.168.0.235/24")
    assert ufw[:5] == ["ufw", "allow", "from", "192.168.0.0/24", "to"] and "8765" in ufw and "tcp" in ufw
    assert network.firewall_remove_command("ufw", 8765, "192.168.0.0/24")[:2] == ["ufw", "delete"]
    fwd = network.firewall_command("firewalld", 8765, "10.0.0.0/24")
    assert fwd[1] == "--permanent" and 'source address="10.0.0.0/24"' in fwd[2] and 'port="8765"' in fwd[2]
    assert network.firewall_command("other", 1, "10.0.0.0/8") == []


def test_firewall_state_from_systemd():
    r = Runner({("systemctl", "show", "--no-pager", "-p", "LoadState", "-p", "ActiveState", "-p", "SubState", "-p",
                 "UnitFileState", "--", "ufw.service"): (0, "LoadState=loaded\nActiveState=active\n", "")})
    assert network.firewall(r) == {"active": True, "ufw": True, "firewalld": False}


def test_public_ip_accepts_only_an_ipv4(monkeypatch):
    async def go(answer):
        async def handler(request):
            return web.Response(text=answer)

        app = web.Application()
        app.router.add_get("/", handler)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "127.0.0.1", 0)
        await site.start()
        monkeypatch.setattr(network, "PUBLIC_IP_SERVICE", f"http://127.0.0.1:{site._server.sockets[0].getsockname()[1]}/")
        import aiohttp
        try:
            async with aiohttp.ClientSession() as http:
                return await network.public_ip(http)
        finally:
            await runner.cleanup()

    assert asyncio.run(go("203.0.113.7\n")) == "203.0.113.7"
    with pytest.raises(ValueError):
        asyncio.run(go("<html>blocked</html>"))
