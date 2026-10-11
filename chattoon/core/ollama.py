"""Async client for the local Ollama API (https://github.com/ollama/ollama/blob/main/docs/api.md)."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from dataclasses import dataclass, field

import aiohttp

# Small models with good Brazilian Portuguese, in order of preference. They are only
# suggestions: any installed chat model can be selected.
RECOMMENDED_MODELS = ("gemma3:4b", "qwen3.5:4b", "qwen3:4b", "llama3.2:3b", "gemma3:1b", "qwen3.5:2b")


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

    @property
    def size_gb(self) -> float:
        return round(self.size / 1e9, 2)


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

    async def capabilities(self, model: str) -> list[str]:
        if model not in self._capabilities:
            data = await self._json("POST", "/api/show", {"model": model})
            self._capabilities[model] = list(data.get("capabilities") or ["completion"])
        return self._capabilities[model]

    async def pull(self, model: str, progress: Callable[[str, int, int], None] | None = None) -> None:
        """Download a model, reporting (status, completed, total)."""
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
        except aiohttp.ClientConnectorError as e:
            raise OllamaUnavailable(f"Ollama is not reachable at {self.host}") from e

    async def preload(self, model: str, keep_alive: str = "15m") -> None:
        """Load the model into memory so the first viewer does not wait for it."""
        await self._json("POST", "/api/generate", {"model": model, "keep_alive": keep_alive}, timeout=180)

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
