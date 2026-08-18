"""Minimal NVIDIA NIM client.

Deliberately built on urllib from the standard library rather than the openai
SDK or requests. The tool is meant to run on locked-down machines where adding
packages is friction, and the endpoint is an ordinary JSON POST.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

BASE_URL = "https://integrate.api.nvidia.com/v1"
DEFAULT_MODEL = "meta/llama-3.3-70b-instruct"
DEFAULT_TIMEOUT = 120


class AIUnavailable(RuntimeError):
    """Raised when the AI path cannot run: no key, no network, bad response.

    Always recoverable -- callers fall back to the deterministic path and
    record that the AI step did not happen. The tool never fails because an
    optional model call failed.
    """


@dataclass
class Usage:
    calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0

    def add(self, payload: Dict[str, Any]) -> None:
        u = payload.get("usage") or {}
        self.calls += 1
        self.prompt_tokens += int(u.get("prompt_tokens") or 0)
        self.completion_tokens += int(u.get("completion_tokens") or 0)


@dataclass
class NvidiaClient:
    api_key: str
    model: str = DEFAULT_MODEL
    base_url: str = BASE_URL
    timeout: int = DEFAULT_TIMEOUT
    temperature: float = 0.0          # determinism matters more than variety here
    max_tokens: int = 4096
    retries: int = 2
    usage: Usage = field(default_factory=Usage)

    def complete(self, system: str, user: str, *, json_object: bool = True) -> str:
        body: Dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": self.temperature,
            "top_p": 1,
            "max_tokens": self.max_tokens,
            "stream": False,
        }
        if json_object:
            # Supported by most NIM chat models; harmless where it is ignored,
            # and the caller re-parses defensively either way.
            body["response_format"] = {"type": "json_object"}

        last: Optional[Exception] = None
        for attempt in range(self.retries + 1):
            try:
                payload = self._post("/chat/completions", body)
                self.usage.add(payload)
                choices = payload.get("choices") or []
                if not choices:
                    raise AIUnavailable("model returned no choices")
                return (choices[0].get("message") or {}).get("content") or ""
            except AIUnavailable:
                raise
            except Exception as exc:  # network, decode, transient 5xx
                last = exc
                if attempt < self.retries:
                    time.sleep(1.5 * (attempt + 1))
        raise AIUnavailable(f"NVIDIA API call failed after {self.retries + 1} attempts: {last}")

    def _post(self, path: str, body: Dict[str, Any]) -> Dict[str, Any]:
        req = urllib.request.Request(
            self.base_url.rstrip("/") + path,
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:400]
            if exc.code in (401, 403):
                raise AIUnavailable(f"NVIDIA API rejected the key (HTTP {exc.code}). {detail}")
            if exc.code == 404:
                raise AIUnavailable(f"model {self.model!r} not found at {self.base_url}. {detail}")
            raise RuntimeError(f"HTTP {exc.code}: {detail}") from exc

    def describe(self) -> str:
        return f"NVIDIA NIM · {self.model}"


def client_from_env(model: Optional[str] = None) -> NvidiaClient:
    """Build a client from NVIDIA_API_KEY. Raises AIUnavailable when unset, so
    every caller has to handle the no-key case explicitly."""
    key = os.environ.get("NVIDIA_API_KEY", "").strip()
    if not key:
        raise AIUnavailable(
            "NVIDIA_API_KEY is not set. AI assistance is off; the deterministic "
            "checks are unaffected. Get a key at https://build.nvidia.com and "
            "export NVIDIA_API_KEY=nvapi-..."
        )
    return NvidiaClient(
        api_key=key,
        model=model or os.environ.get("PROTOCOLQC_AI_MODEL", DEFAULT_MODEL),
        base_url=os.environ.get("NVIDIA_BASE_URL", BASE_URL),
    )


def list_models(timeout: int = 15) -> List[str]:
    """Model ids the endpoint advertises. Public, needs no key -- used to give
    a useful error when someone names a model that does not exist."""
    try:
        with urllib.request.urlopen(BASE_URL + "/models", timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return sorted(m.get("id", "") for m in data.get("data", []))
    except Exception as exc:
        raise AIUnavailable(f"could not list models: {exc}") from exc
