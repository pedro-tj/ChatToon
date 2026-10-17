"""What this computer has (CPU, memory, GPU), read from /proc and /sys — no command, no network.

Used only to *suggest* models that fit; nothing is ever blocked because of it.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

_VENDORS = {"0x10de": "nvidia", "0x1002": "amd", "0x8086": "intel"}


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def cpu(proc: Path = Path("/proc")) -> dict:
    text = _read(proc / "cpuinfo")
    name = next((ln.split(":", 1)[1].strip() for ln in text.splitlines() if ln.lower().startswith("model name")), "")
    return {"name": re.sub(r"\s+", " ", name), "threads": os.cpu_count() or 0}


def memory(proc: Path = Path("/proc")) -> dict:
    values = {}
    for line in _read(proc / "meminfo").splitlines():
        m = re.match(r"(\w+):\s+(\d+) kB", line)
        if m:
            values[m.group(1)] = int(m.group(2)) * 1024
    return {"total": values.get("MemTotal", 0), "available": values.get("MemAvailable", 0)}


def gpus(sys_root: Path = Path("/sys")) -> list[dict]:
    """Display adapters with their vendor and, for AMD, the dedicated memory."""
    out = []
    drm = sys_root / "class" / "drm"
    seen = set()
    try:
        cards = sorted(p for p in drm.iterdir() if re.fullmatch(r"card\d+", p.name))
    except OSError:
        cards = []
    for card in cards:
        device = card / "device"
        vendor = _read(device / "vendor").strip().lower()
        ident = (vendor, _read(device / "device").strip(), os.path.realpath(device))
        if not vendor or ident in seen:
            continue
        seen.add(ident)
        vram = _read(device / "mem_info_vram_total").strip()  # amdgpu only
        boot = _read(device / "boot_vga").strip() == "1"
        out.append({"vendor": _VENDORS.get(vendor, "other"), "vram": int(vram) if vram.isdigit() else 0,
                    "primary": boot, "driver": os.path.basename(os.path.realpath(device / "driver"))})
    # the dedicated card first (most VRAM), integrated graphics after
    return sorted(out, key=lambda g: (-g["vram"], not g["primary"]))


def summary() -> dict:
    gpu_list = gpus()
    best = gpu_list[0] if gpu_list else {}
    return {"cpu": cpu(), "memory": memory(), "gpus": gpu_list, "gpuVendor": best.get("vendor", ""),
            "vram": max((g["vram"] for g in gpu_list), default=0)}


def acceleration_package(vendor: str) -> str:
    """The Arch/BigLinux Ollama add-on that uses this GPU ("" = CPU only).

    Vulkan works on AMD and Intel and is a small download; NVIDIA has CUDA. ROCm (AMD,
    ~1 GB) stays a manual choice."""
    return {"nvidia": "ollama-cuda", "amd": "ollama-vulkan", "intel": "ollama-vulkan"}.get(vendor, "")


def fits(model_bytes: int, hw: dict) -> str:
    """Rough fit of a model for this computer: good | ok | heavy | unknown (never a block)."""
    if model_bytes <= 0:
        return "unknown"
    vram, ram = hw.get("vram", 0), hw.get("memory", {}).get("total", 0)
    need = model_bytes * 1.25  # weights plus a 4k context and runtime buffers
    if vram and need <= vram:
        return "good"
    if ram and need <= ram * 0.5:
        return "ok"  # fits in RAM; slower on the CPU
    if ram:
        return "heavy"
    return "unknown"
