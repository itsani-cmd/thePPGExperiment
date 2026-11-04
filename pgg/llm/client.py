"""OpenAI-compatible LLM client with retries, timeouts, and usage logging.

The client is intentionally thin: it takes chat messages, returns raw text plus
a usage record. Prompt building, JSON parsing, and validation live in the agent
layer so the client stays reusable and easy to mock. Base URL and key come from
``PGG_BASE_URL`` / ``PGG_API_KEY`` (never logged).
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from ..config import ModelConfig


@dataclass
class CallResult:
    text: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    latency_s: float = 0.0
    retries: int = 0
    error: Optional[str] = None
    model: str = ""


# very rough fallback price table ($ per 1K tokens); only used for estimates
_DEFAULT_PRICES = {"prompt": 0.0, "completion": 0.0}


class LLMClient:
    """Wraps the ``openai`` client against an OpenAI-compatible endpoint."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        timeout_s: float = 60.0,
        max_retries: int = 4,
    ):
        self.base_url = base_url or os.environ.get("PGG_BASE_URL")
        self.api_key = api_key or os.environ.get("PGG_API_KEY") or "sk-noauth"
        self.timeout_s = timeout_s
        self.max_retries = max_retries
        self._client = None  # lazily created so offline/mock runs need no openai

    def _ensure_client(self):
        if self._client is None:
            try:
                from openai import OpenAI
            except Exception as exc:  # pragma: no cover - import guard
                raise RuntimeError(
                    "The 'openai' package is required for LLM agents. "
                    "Install it or use --agents mock."
                ) from exc
            self._client = OpenAI(
                base_url=self.base_url,
                api_key=self.api_key,
                timeout=self.timeout_s,
            )
        return self._client

    def list_models(self) -> List[str]:
        client = self._ensure_client()
        try:
            resp = client.models.list()
            return [m.id for m in resp.data]
        except Exception:
            return []

    def chat(
        self,
        model_cfg: ModelConfig,
        messages: List[Dict[str, str]],
        json_mode: Optional[bool] = None,
    ) -> CallResult:
        """One chat completion with exponential backoff on 429/5xx."""
        client = self._ensure_client()
        use_json = model_cfg.json_mode if json_mode is None else json_mode

        kwargs: Dict[str, object] = {
            "model": model_cfg.model,
            "messages": messages,
            "temperature": model_cfg.temperature,
            "max_tokens": model_cfg.max_tokens,
        }
        if use_json:
            kwargs["response_format"] = {"type": "json_object"}
        if model_cfg.reasoning:
            # Some OpenAI-compatible endpoints accept a reasoning effort hint.
            kwargs["reasoning_effort"] = model_cfg.reasoning

        delay = 1.0
        last_err: Optional[str] = None
        start = time.time()
        for attempt in range(self.max_retries + 1):
            try:
                resp = client.chat.completions.create(**kwargs)
                text = resp.choices[0].message.content or ""
                usage = getattr(resp, "usage", None)
                return CallResult(
                    text=text,
                    prompt_tokens=getattr(usage, "prompt_tokens", 0) or 0,
                    completion_tokens=getattr(usage, "completion_tokens", 0) or 0,
                    total_tokens=getattr(usage, "total_tokens", 0) or 0,
                    latency_s=time.time() - start,
                    retries=attempt,
                    model=model_cfg.model,
                )
            except Exception as exc:  # pragma: no cover - network dependent
                last_err = f"{type(exc).__name__}: {exc}"
                status = getattr(exc, "status_code", None)
                retryable = status in (429, 500, 502, 503, 504) or status is None
                if attempt < self.max_retries and retryable:
                    time.sleep(delay)
                    delay = min(delay * 2, 30.0)
                    continue
                break
        return CallResult(
            text="",
            latency_s=time.time() - start,
            retries=self.max_retries,
            error=last_err,
            model=model_cfg.model,
        )


def estimate_cost(prompt_tokens: int, completion_tokens: int, prices=None) -> float:
    prices = prices or _DEFAULT_PRICES
    return (
        prompt_tokens / 1000.0 * prices.get("prompt", 0.0)
        + completion_tokens / 1000.0 * prices.get("completion", 0.0)
    )
