"""Where logins live: the desktop keyring, never the settings file.

ChatToon never asks for passwords. What it keeps are OAuth tokens (Twitch), app secrets
and tokens the streamer pasted (Kick, Meta, X). They are stored with the Secret Service
API (KWallet on Plasma, GNOME Keyring, KeePassXC…) through libsecret. Only when no
keyring is running they go to ``~/.local/share/chattoon/credentials.json`` with 0600
permissions, and the interface says so.

Every value stored is also registered with :data:`REDACTOR`, so it can never appear in
a log line even if some library logs a request URL.
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
from pathlib import Path

from .config import data_dir

log = logging.getLogger(__name__)

SCHEMA_NAME = "org.biglinux.ChatToon"


class Redactor(logging.Filter):
    """Masks secrets in log records (known values plus token-looking patterns)."""

    _PATTERNS = (
        re.compile(r"((?:access|refresh|id)_token|client_secret|device_code|code_verifier|token|password|"
                   r"oauth_token|api_key)([\"']?\s*[=:]\s*[\"']?)([^&\s\"',}]+)", re.I),
        re.compile(r"(Bearer|OAuth)\s+[A-Za-z0-9._~+/=-]+", re.I),
        re.compile(r"(oauth:)[A-Za-z0-9]+", re.I),
    )

    def __init__(self) -> None:
        super().__init__()
        self._values: set[str] = set()
        self._lock = threading.Lock()

    def add(self, *values: str) -> None:
        with self._lock:
            self._values.update(v for v in values if isinstance(v, str) and len(v) >= 8)

    def clean(self, text: str) -> str:
        with self._lock:
            values = sorted(self._values, key=len, reverse=True)
        for value in values:
            if value in text:
                text = text.replace(value, "***")
        text = self._PATTERNS[0].sub(lambda m: f"{m.group(1)}{m.group(2)}***", text)
        text = self._PATTERNS[1].sub(lambda m: f"{m.group(1)} ***", text)
        return self._PATTERNS[2].sub(r"\1***", text)

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:  # noqa: BLE001 - a broken record must still be logged
            return True
        cleaned = self.clean(message)
        if cleaned != message:
            record.msg, record.args = cleaned, ()
        if record.exc_text:
            record.exc_text = self.clean(record.exc_text)
        return True


REDACTOR = Redactor()


def install_log_redaction() -> None:
    """Attach the redactor to every root handler (call after logging.basicConfig)."""
    root = logging.getLogger()
    for handler in root.handlers:
        if REDACTOR not in handler.filters:
            handler.addFilter(REDACTOR)
    if REDACTOR not in root.filters:
        root.addFilter(REDACTOR)


def _remember_secrets(value: dict) -> None:
    for v in value.values():
        if isinstance(v, str):
            REDACTOR.add(v)


class CredentialStore:
    """Small key -> dict store. Keys look like ``twitch/account`` or ``kick/app``."""

    backend = "memory"
    encrypted = False

    def __init__(self) -> None:
        self._cache: dict[str, dict] = {}

    def get(self, key: str) -> dict | None:
        value = self._cache.get(key)
        return dict(value) if value is not None else None

    def set(self, key: str, value: dict) -> None:
        _remember_secrets(value)
        self._cache[key] = dict(value)

    def delete(self, key: str) -> None:
        self._cache.pop(key, None)

    def has(self, key: str) -> bool:
        return self.get(key) is not None


class FileCredentialStore(CredentialStore):
    """Fallback when no Secret Service is running: a private JSON file (0600)."""

    backend = "file"

    def __init__(self, path: Path | None = None) -> None:
        super().__init__()
        self.path = path or data_dir() / "credentials.json"
        self._lock = threading.Lock()
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                self._cache = {k: v for k, v in data.items() if isinstance(v, dict)}
                for v in self._cache.values():
                    _remember_secrets(v)
        except (OSError, ValueError):
            pass

    def _write(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(self._cache, f)
        os.chmod(tmp, 0o600)
        tmp.replace(self.path)

    def set(self, key: str, value: dict) -> None:
        with self._lock:
            super().set(key, value)
            self._write()

    def delete(self, key: str) -> None:
        with self._lock:
            super().delete(key)
            if self._cache:
                self._write()
            else:
                self.path.unlink(missing_ok=True)


class SecretServiceStore(CredentialStore):
    """libsecret (Secret Service D-Bus API). Calls block: use them from worker threads."""

    backend = "secret-service"
    encrypted = True

    def __init__(self) -> None:
        super().__init__()
        import gi

        gi.require_version("Secret", "1")
        from gi.repository import Secret

        self._secret = Secret
        self._schema = Secret.Schema.new(SCHEMA_NAME, Secret.SchemaFlags.NONE,
                                         {"account": Secret.SchemaAttributeType.STRING})
        self._loaded: set[str] = set()

    def get(self, key: str) -> dict | None:
        if key not in self._loaded:
            raw = self._secret.password_lookup_sync(self._schema, {"account": key}, None)
            self._loaded.add(key)
            if raw:
                try:
                    value = json.loads(raw)
                    if isinstance(value, dict):
                        super().set(key, value)
                except ValueError:
                    log.warning("ignoring an unreadable keyring entry")
        return super().get(key)

    def set(self, key: str, value: dict) -> None:
        ok = self._secret.password_store_sync(self._schema, {"account": key}, self._secret.COLLECTION_DEFAULT,
                                              f"ChatToon — {key}", json.dumps(value), None)
        if not ok:
            raise OSError("the keyring refused to store the credential")
        super().set(key, value)
        self._loaded.add(key)

    def delete(self, key: str) -> None:
        self._secret.password_clear_sync(self._schema, {"account": key}, None)
        super().delete(key)
        self._loaded.add(key)


def open_store() -> CredentialStore:
    """The best store available. ``CHATTOON_CREDENTIALS=memory|file`` forces one (tests)."""
    forced = os.environ.get("CHATTOON_CREDENTIALS", "")
    if forced == "memory":
        return CredentialStore()
    if forced != "file":
        try:
            store = SecretServiceStore()
            store._secret.password_lookup_sync(store._schema, {"account": "chattoon/probe"}, None)
            return store
        except Exception as e:  # noqa: BLE001 - no gi, no D-Bus session or no keyring daemon
            log.info("no Secret Service keyring (%s); using a private file", type(e).__name__)
    return FileCredentialStore()
