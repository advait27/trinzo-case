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
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

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
    key_origin: str = "supplied directly"
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

    def describe_key(self) -> str:
        """Which key, and where it was found. Masked -- the tool never prints a
        key in full, including into a console log a reviewer might later attach
        to a record."""
        return f"{mask(self.api_key)} (from {self.key_origin})"


# ---- where the key comes from -------------------------------------------
#
# Two places, checked in this order:
#   1. the NVIDIA_API_KEY environment variable
#   2. a .env file at the project root (gitignored)
#
# The file exists because "export it in your shell" is a poor instruction on a
# shared or demonstration machine: the key lands in terminal scrollback and in
# shell history, and a server that read the environment once at startup has to
# be killed and restarted to pick up a new one. Resolution happens per call, so
# a key written into .env is live on the very next request.
#
# The environment still wins, because that is what CI and container runtimes
# set, and a stale checked-out file should never quietly override them.

ENV_FILENAMES = (".env.local", ".env")


def _search_dirs() -> List[Path]:
    """Directories searched for a .env file. A function rather than a constant
    so tests can point it somewhere harmless -- a test that starts failing
    because the machine it runs on happens to be configured is not a test."""
    out: List[Path] = []
    for d in (Path.cwd(), Path(__file__).resolve().parents[2]):
        if d not in out:
            out.append(d)
    return out


def _parse_env_file(text: str) -> Dict[str, str]:
    """Small KEY=value parser, rather than a dependency on python-dotenv. The
    whole install story is "python, one dependency"; adding a second one to
    read six lines of text would not be a good trade.

    Deliberately does not strip trailing "# comments": a key is an opaque
    string, and silently truncating one at a character it might contain would
    produce a baffling 401 rather than an honest error."""
    out: Dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export "):]
        name, _, value = line.partition("=")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        out[name.strip()] = value
    return out


def resolve(name: str) -> Tuple[str, str]:
    """Return (value, where it came from). An empty value means "not configured
    anywhere". The origin is reported so a run can say which key it used
    without ever printing the key itself."""
    value = os.environ.get(name, "").strip()
    if value:
        return value, f"{name} environment variable"
    for directory in _search_dirs():
        for filename in ENV_FILENAMES:
            path = directory / filename
            try:
                if not path.is_file():
                    continue
                found = _parse_env_file(path.read_text(encoding="utf-8")).get(name, "").strip()
            except OSError:
                continue
            if found:
                return found, str(path)
    return "", ""


def mask(key: str) -> str:
    """Enough to tell two keys apart, not enough to use one. Everywhere the
    tool reports which key it is holding goes through here."""
    if len(key) <= 8:
        return "*" * len(key)
    return f"{key[:6]}...{key[-4:]}"


NO_KEY_MESSAGE = (
    "No NVIDIA API key found. AI assistance is off; the deterministic checks "
    "are unaffected. Get a key at https://build.nvidia.com, then either write "
    "NVIDIA_API_KEY=nvapi-... into a .env file at the project root, or export "
    "NVIDIA_API_KEY in the shell. A key in .env is picked up without a restart."
)


def client_from_env(model: Optional[str] = None) -> NvidiaClient:
    """Build a client from a resolved key. Raises AIUnavailable when there is
    none, so every caller has to handle the no-key case explicitly."""
    key, origin = resolve("NVIDIA_API_KEY")
    if not key:
        raise AIUnavailable(NO_KEY_MESSAGE)
    return NvidiaClient(
        api_key=key,
        model=model or resolve("PROTOCOLQC_AI_MODEL")[0] or DEFAULT_MODEL,
        base_url=resolve("NVIDIA_BASE_URL")[0] or BASE_URL,
        key_origin=origin,
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
