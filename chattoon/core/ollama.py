"""Async client for the local Ollama API (https://github.com/ollama/ollama/blob/main/docs/api.md)."""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field

import aiohttp

# Small models with good Brazilian Portuguese, in order of preference. They are only
# suggestions: any installed chat model can be selected.
RECOMMENDED_MODELS = ("gemma3:4b", "qwen3.5:4b", "qwen3:4b", "llama3.2:3b", "gemma3:1b", "qwen3.5:2b")

# What the suggestion cards say about each model. Download sizes were measured from the
# registry manifests (registry.ollama.ai, 2026-10-17) and are shown as approximate; the
# confirmation dialog reads the exact size again before downloading.
SUGGESTED = (
    {"name": "gemma3:4b", "params": "4B", "bytes": 3_350_000_000, "features": ["vision"], "languages": "pt, en, es +140",
     "tier": "balanced"},
    {"name": "qwen3.5:4b", "params": "4B", "bytes": 3_320_000_000, "features": ["vision", "tools"],
     "languages": "pt, en, es +200", "tier": "balanced"},
    {"name": "qwen3:4b", "params": "4B", "bytes": 2_500_000_000, "features": ["tools"], "languages": "pt, en, es +100",
     "tier": "balanced"},
    {"name": "llama3.2:3b", "params": "3B", "bytes": 2_020_000_000, "features": ["tools"], "languages": "pt, en, es +5",
     "tier": "light"},
    {"name": "qwen3.5:2b", "params": "2B", "bytes": 2_680_000_000, "features": ["vision", "tools"],
     "languages": "pt, en, es +200", "tier": "light"},
    {"name": "gemma3:1b", "params": "1B", "bytes": 810_000_000, "features": [], "languages": "en (pt limited)",
     "tier": "tiny"},
    {"name": "llama3.1:8b", "params": "8B", "bytes": 4_920_000_000, "features": ["tools"], "languages": "pt, en, es +5",
     "tier": "strong"},
    {"name": "qwen3:8b", "params": "8B", "bytes": 5_230_000_000, "features": ["tools"], "languages": "pt, en, es +100",
     "tier": "strong"},
    {"name": "gemma3:12b", "params": "12B", "bytes": 8_160_000_000, "features": ["vision"],
     "languages": "pt, en, es +140", "tier": "strong"},
)
REGISTRY = "https://registry.ollama.ai"
# [host/][namespace/]model[:tag] — e.g. gemma3:4b, user/model, hf.co/user/Repo-GGUF:Q4_K_M
_MODEL_REF = re.compile(r"^(?:[A-Za-z0-9][A-Za-z0-9._-]{0,80}/){0,2}[A-Za-z0-9][A-Za-z0-9._-]{0,120}(?::[A-Za-z0-9._-]{1,80})?$")


class OllamaError(Exception):
    pass


class OllamaUnavailable(OllamaError):
    """The service is not running or not reachable."""


class ModelNotFound(OllamaError):
    pass


@dataclass
class ModelInfo:
    name: str
    size: int = 0
    family: str = ""
    parameters: str = ""
    quantization: str = ""
    format: str = ""
    families: list[str] = field(default_factory=list)
    modified: str = ""
    capabilities: list[str] = field(default_factory=list)
    capabilities_known: bool = False  # False: old Ollama without "capabilities", guessed from the family
    context_length: int = 0
    remote: bool = False  # an Ollama Cloud model: answered by ollama.com, not this computer
    error: str = ""  # /api/show failed for it

    @property
    def size_gb(self) -> float:
        return round(self.size / 1e9, 2)

    @property
    def chat(self) -> bool:
        """Can it answer the chat? Only models that complete text (not embedding-only ones)."""
        return not self.error and "completion" in self.capabilities

    @property
    def reason(self) -> str:
        """Why it cannot be chosen to answer the chat ("" = it can)."""
        if self.error:
            return "unreadable"
        if self.chat:
            return ""
        return "embedding" if "embedding" in self.capabilities else "no-completion"

    @property
    def kind(self) -> str:
        if "embedding" in self.capabilities and not self.chat:
            return "embedding"
        return "vision" if "vision" in self.capabilities else "chat" if self.chat else "other"

    def to_dict(self) -> dict:
        return {"name": self.name, "size": self.size, "sizeGb": self.size_gb, "family": self.family,
                "parameters": self.parameters, "quantization": self.quantization, "format": self.format,
                "capabilities": list(self.capabilities), "capabilitiesKnown": self.capabilities_known,
                "contextLength": self.context_length, "remote": self.remote, "chat": self.chat,
                "reason": self.reason, "kind": self.kind, "error": self.error, "modified": self.modified}


def _guess_capabilities(name: str, family: str, families: list[str]) -> list[str]:
    text = " ".join([name, family, *families]).lower()
    return ["embedding"] if "embed" in text or "bert" in text else ["completion"]


def valid_model_name(name: str) -> bool:
    """A model reference Ollama accepts (``gemma3:4b``, ``user/model:tag``…). Checked before
    anything is downloaded, so pasted text never becomes a request path."""
    return bool(_MODEL_REF.match(name.strip()))


@dataclass
class ChatResult:
    text: str
    model: str
    eval_count: int = 0
    total_seconds: float = 0.0
    load_seconds: float = 0.0
    raw: dict = field(default_factory=dict, repr=False)


class OllamaClient:
    def __init__(self, host: str = "http://127.0.0.1:11434", timeout: float = 60.0):
        self.host = host.rstrip("/")
        self.timeout = timeout
        self._capabilities: dict[str, list[str]] = {}
        self._session: aiohttp.ClientSession | None = None

    async def __aenter__(self) -> OllamaClient:
        return self

    async def __aexit__(self, *exc) -> None:
        await self.close()

    def _http(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=None, sock_connect=5))
        return self._session

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

    async def _json(self, method: str, path: str, payload: dict | None = None, timeout: float = 15) -> dict:
        try:
            async with self._http().request(method, self.host + path, json=payload,
                                            timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
                data = await resp.json(content_type=None)
                if resp.status == 404 and "not found" in str(data.get("error", "")).lower():
                    raise ModelNotFound(data["error"])
                if resp.status >= 400:
                    raise OllamaError(data.get("error") or f"HTTP {resp.status}")
                return data
        except (aiohttp.ClientConnectorError, aiohttp.ServerDisconnectedError) as e:
            raise OllamaUnavailable(f"Ollama is not reachable at {self.host}") from e
        except asyncio.TimeoutError as e:
            raise OllamaUnavailable(f"Ollama did not answer within {timeout:.0f}s") from e
        except (aiohttp.ContentTypeError, json.JSONDecodeError) as e:
            raise OllamaError("Unexpected response from Ollama") from e

    # -- discovery --------------------------------------------------------

    async def version(self) -> str:
        return (await self._json("GET", "/api/version", timeout=5)).get("version", "")

    async def list_models(self) -> list[ModelInfo]:
        data = await self._json("GET", "/api/tags")
        models = []
        for m in data.get("models", []):
            d = m.get("details") or {}
            if "embed" in (d.get("family", "") + m.get("name", "")).lower():
                continue  # embedding models cannot chat
            models.append(ModelInfo(m.get("name", ""), m.get("size", 0), d.get("family", ""),
                                    d.get("parameter_size", ""), d.get("quantization_level", "")))
        return sorted(models, key=lambda m: m.name)

    async def show(self, model: str) -> dict:
        return await self._json("POST", "/api/show", {"model": model}, timeout=20)

    async def catalog(self) -> list[ModelInfo]:
        """Every installed model — chat, vision, embedding, imported or from another namespace —
        with what it can do (``/api/show`` capabilities). Nothing is hidden: models that cannot
        chat are returned too, with the reason, so the interface can explain them."""
        data = await self._json("GET", "/api/tags")
        models: list[ModelInfo] = []
        for m in data.get("models") or []:
            if not isinstance(m, dict) or not m.get("name"):
                continue
            d = m.get("details") or {}
            models.append(ModelInfo(
                str(m.get("name") or m.get("model")), int(m.get("size") or 0), str(d.get("family") or ""),
                str(d.get("parameter_size") or ""), str(d.get("quantization_level") or ""), str(d.get("format") or ""),
                [str(f) for f in (d.get("families") or []) if f], str(m.get("modified_at") or ""),
                remote=bool(m.get("remote_host") or m.get("remote_model"))))
        gate = asyncio.Semaphore(4)

        async def inspect(info: ModelInfo) -> None:
            async with gate:
                try:
                    shown = await self.show(info.name)
                except OllamaUnavailable:
                    raise
                except OllamaError as e:
                    info.error = str(e)[:200]
                    info.capabilities = _guess_capabilities(info.name, info.family, info.families)
                    return
            caps = shown.get("capabilities")
            if isinstance(caps, list) and caps:
                info.capabilities, info.capabilities_known = [str(c) for c in caps], True
            else:
                info.capabilities = _guess_capabilities(info.name, info.family, info.families)
            self._capabilities[info.name] = info.capabilities
            model_info = shown.get("model_info") or {}
            if isinstance(model_info, dict):
                ctx = next((v for k, v in model_info.items() if str(k).endswith(".context_length")), 0)
                info.context_length = int(ctx) if isinstance(ctx, (int, float)) else 0

        await asyncio.gather(*(inspect(m) for m in models))
        return sorted(models, key=lambda m: m.name.lower())

    async def running(self) -> list[dict]:
        """Models loaded in memory right now (``/api/ps``)."""
        data = await self._json("GET", "/api/ps", timeout=5)
        return [{"name": str(m.get("name", "")), "vram": int(m.get("size_vram") or 0),
                 "size": int(m.get("size") or 0), "expires": str(m.get("expires_at") or "")}
                for m in data.get("models") or [] if isinstance(m, dict)]

    async def capabilities(self, model: str) -> list[str]:
        if model not in self._capabilities:
            data = await self._json("POST", "/api/show", {"model": model})
            self._capabilities[model] = list(data.get("capabilities") or ["completion"])
        return self._capabilities[model]

    async def pull(self, model: str, progress: Callable[[str, int, int], None] | None = None,
                   on_event: Callable[[dict], None] | None = None) -> None:
        """Download a model, reporting (status, completed, total) — of the layer being pulled —
        and, with ``on_event``, every raw event (it carries the layer ``digest``)."""
        try:
            async with self._http().post(self.host + "/api/pull", json={"model": model, "stream": True},
                                         timeout=aiohttp.ClientTimeout(total=None, sock_read=300)) as resp:
                async for line in resp.content:
                    if not line.strip():
                        continue
                    event = json.loads(line)
                    if event.get("error"):
                        raise OllamaError(event["error"])
                    if progress:
                        progress(event.get("status", ""), int(event.get("completed") or 0),
                                 int(event.get("total") or 0))
                    if on_event:
                        on_event(event)
        except aiohttp.ClientConnectorError as e:
            raise OllamaUnavailable(f"Ollama is not reachable at {self.host}") from e

    async def preload(self, model: str, keep_alive: str = "15m", context_window: int | None = None) -> None:
        """Load the model into memory so the first viewer does not wait for it. With the
        same ``num_ctx`` as the chat calls — another size would make Ollama load it again."""
        payload: dict = {"model": model, "keep_alive": keep_alive}
        if context_window:
            payload["options"] = {"num_ctx": context_window}
        await self._json("POST", "/api/generate", payload, timeout=180)

    # -- chat -------------------------------------------------------------

    async def chat(
        self,
        model: str,
        messages: list[dict],
        *,
        temperature: float = 0.9,
        max_tokens: int = 160,
        context_window: int = 4096,
        schema: dict | None = None,
        keep_alive: str = "15m",
        on_token: Callable[[str], None] | None = None,
        timeout: float | None = None,
    ) -> ChatResult:
        """Stream a chat completion. Cancel the awaiting task to interrupt generation."""
        payload: dict = {
            "model": model,
            "messages": messages,
            "stream": True,
            "keep_alive": keep_alive,
            "options": {"temperature": temperature, "num_predict": max_tokens, "num_ctx": context_window},
        }
        if schema:
            payload["format"] = schema
        if "thinking" in await self.capabilities(model):
            payload["think"] = False  # reasoning traces only add latency for short banter

        async def run() -> ChatResult:
            parts: list[str] = []
            final: dict = {}
            try:
                async with self._http().post(self.host + "/api/chat", json=payload,
                                             timeout=aiohttp.ClientTimeout(total=None, sock_connect=5)) as resp:
                    if resp.status >= 400:
                        data = await resp.json(content_type=None)
                        msg = data.get("error") or f"HTTP {resp.status}"
                        raise (ModelNotFound if resp.status == 404 else OllamaError)(msg)
                    async for line in resp.content:
                        if not line.strip():
                            continue
                        event = json.loads(line)
                        if event.get("error"):
                            raise OllamaError(event["error"])
                        chunk = (event.get("message") or {}).get("content", "")
                        if chunk:
                            parts.append(chunk)
                            if on_token:
                                on_token(chunk)
                        if event.get("done"):
                            final = event
                            break
            except aiohttp.ClientConnectorError as e:
                raise OllamaUnavailable(f"Ollama is not reachable at {self.host}") from e
            text = "".join(parts).strip()
            if not text:
                raise OllamaError("The model returned an empty answer")
            return ChatResult(
                text=text, model=model, eval_count=int(final.get("eval_count") or 0),
                total_seconds=(final.get("total_duration") or 0) / 1e9,
                load_seconds=(final.get("load_duration") or 0) / 1e9, raw=final,
            )

        try:
            return await asyncio.wait_for(run(), timeout or self.timeout)
        except asyncio.TimeoutError as e:
            raise OllamaError(f"The model took longer than {timeout or self.timeout:.0f}s") from e


async def registry_size(model: str, session, timeout: float = 10) -> int:
    """Exact download size of a model from its registry manifest (0 when unknown). Asked only
    when the person is about to download it from that same registry."""
    import aiohttp

    if not valid_model_name(model):
        return 0
    name, _, tag = model.partition(":")
    if name.count("/") > 1:
        return 0  # another host (hf.co/…): its size is reported by the download itself
    path = name if "/" in name else f"library/{name}"
    url = f"{REGISTRY}/v2/{path}/manifests/{tag or 'latest'}"
    try:
        async with session.get(url, headers={"Accept": "application/vnd.docker.distribution.manifest.v2+json"},
                               timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
            if resp.status != 200:
                return 0
            data = await resp.json(content_type=None)
    except (aiohttp.ClientError, asyncio.TimeoutError, ValueError):
        return 0
    return sum(int(layer.get("size") or 0) for layer in data.get("layers") or [] if isinstance(layer, dict))
