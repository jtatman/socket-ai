"""Shared helper to obtain an OpenAI-compatible client pointed at a local Ollama / OpenAI host.

Usage
-----
>>> from core.llm_proxy import get_client
>>> client = get_client("default")
"""
from __future__ import annotations

import os
from functools import lru_cache
from typing import Optional

from openai import OpenAI


@lru_cache(maxsize=None)
def get_client(name: str | None = None) -> OpenAI:
    """Return (and cache) an *OpenAI* client configured via environment variables.

    Parameters
    ----------
    name
        Logical name of the node (e.g. "ollama1"). This is only used to
        namespace environment variables so multiple nodes can coexist:
        ``OLLAMA1_BASE_URL`` / ``OLLAMA1_API_KEY``.

    Environment variables (upper-case):
    • <NAME>_BASE_URL   – http(s)://host:port/v1 (defaults to OLLAMA_BASE_URL)
    • <NAME>_API_KEY    – token (defaults to OLLAMA_API_KEY or "ollama")

    If *name* is *None* the prefix "OLLAMA" is used.
    """
    # If *name* looks like a URL or a bare IP/host, treat it as the actual
    # endpoint of an Ollama-compatible server instead of an environment-variable
    # namespace. This makes it convenient to specify e.g. ``llm_node: 10.0.0.5``
    # in YAML without having to set additional environment variables.
    if name:
        lowered = str(name).lower()
        # Full URL provided → use as-is.
        if lowered.startswith("http://") or lowered.startswith("https://"):
            base_url = lowered.rstrip("/")
            api_key = os.getenv("OLLAMA_API_KEY", "ollama")
            timeout_s = float(os.getenv("LLM_TIMEOUT", "60"))
            return OpenAI(base_url=base_url, api_key=api_key, timeout=timeout_s)
        # Bare IPv4 / hostname (no scheme) → assume default Ollama port 11434.
        if all(c.isdigit() or c == "." for c in lowered) or "." in lowered:
            base_url = f"http://{lowered}:11434/v1"
            api_key = os.getenv("OLLAMA_API_KEY", "ollama")
            timeout_s = float(os.getenv("LLM_TIMEOUT", "60"))
            return OpenAI(base_url=base_url, api_key=api_key, timeout=timeout_s)

    # Fallback to environment-variable based configuration.
    prefix = (name or "OLLAMA").upper()
    base_url: Optional[str] = os.getenv(f"{prefix}_BASE_URL") or os.getenv("OLLAMA_BASE_URL")
    api_key: Optional[str] = os.getenv(f"{prefix}_API_KEY") or os.getenv("OLLAMA_API_KEY", "ollama")

    if not base_url:
        raise RuntimeError(
            f"Environment variable {prefix}_BASE_URL (or OLLAMA_BASE_URL) not set; "
            "cannot reach LLM backend."
        )

    # Timeouts are important when many bots hit the same server.
    timeout_s = float(os.getenv("LLM_TIMEOUT", "60"))

    return OpenAI(base_url=base_url, api_key=api_key, timeout=timeout_s)
