"""Hiding what must not appear on a live stream (docs/34-remote-access-privacy.md).

The overlay token, the public IP and credentials are masked by default everywhere; the
live privacy mode also hides local addresses, domains and account names. Revealing is a
deliberate, temporary action in the interface. These helpers are used for every text that
leaves the engine for the screen (toasts, diagnostics, the start report).
"""

from __future__ import annotations

import ipaddress
import re

MASK = "••••••"
_TOKEN_IN_URL = re.compile(r"(/o/)[A-Za-z0-9_-]{6,}(/?)")
_IPV4 = re.compile(r"(?<![\d.])(\d{1,3}(?:\.\d{1,3}){3})(?![\d.])")
_IPV6 = re.compile(r"(?<![\w:])((?:[0-9a-fA-F]{1,4}:){2,7}[0-9a-fA-F]{1,4})(?![\w:])")


def mask_ip(ip: str) -> str:
    return "***.***.***.***" if ":" not in ip else "****:****:****::****"


def mask_url_token(text: str) -> str:
    """``http://127.0.0.1:8765/o/AbC…/`` → ``http://127.0.0.1:8765/o/••••••/``"""
    return _TOKEN_IN_URL.sub(lambda m: m.group(1) + MASK + m.group(2), text or "")


def scrub(text: str, secrets: tuple[str, ...] = (), live: bool = True) -> str:
    """Mask tokens in URLs, the given secrets and public IPs; in live mode every IP."""
    out = mask_url_token(text or "")
    for secret in sorted((s for s in secrets if s and len(s) >= 6), key=len, reverse=True):
        out = out.replace(secret, MASK)

    def ip4(m: re.Match) -> str:
        try:
            addr = ipaddress.ip_address(m.group(1))
        except ValueError:
            return m.group(1)
        if addr.is_loopback or (not live and not addr.is_global):
            return m.group(1)
        return mask_ip(m.group(1))

    out = _IPV4.sub(ip4, out)

    def ip6(m: re.Match) -> str:
        try:
            addr = ipaddress.ip_address(m.group(1))
        except ValueError:
            return m.group(1)
        return m.group(1) if addr.is_loopback or (not live and not addr.is_global) else mask_ip(m.group(1))

    return _IPV6.sub(ip6, out)
