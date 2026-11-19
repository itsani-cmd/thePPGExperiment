"""LLM-backed agent: builds prompts, calls the client, parses + validates JSON,
retries on invalid output, and falls back to a documented safe default.

A record of every call (prompt, raw response, parsed output, usage, retries,
errors) is appended to ``self.call_log`` so the runner can write calls.jsonl.
Agents are stateless w.r.t. game progress — the observation carries the state.
"""

from __future__ import annotations

import json
from typing import Dict, List, Optional

from pydantic import ValidationError

from ..config import GameConfig, ModelConfig
from ..llm.client import LLMClient
from ..prompts import builder
from .base import (
    ContributionOut,
    IntentProbeOut,
    MessageOut,
    Observation,
    PunishOut,
    RewardOut,
)


def _balanced_objects(text: str) -> List[str]:
    """Return every top-level balanced ``{...}`` span in ``text``, in order.

    Tracks brace depth while respecting string literals and escapes so braces
    inside strings do not break the match.
    """
    spans: List[str] = []
    depth = 0
    start = -1
    in_str = False
    escape = False
    for i, ch in enumerate(text):
        if in_str:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            if depth > 0:
                depth -= 1
                if depth == 0 and start >= 0:
                    spans.append(text[start : i + 1])
                    start = -1
    return spans


def extract_json(text: str) -> Optional[dict]:
    """Return the last valid JSON object in ``text``, or None.

    Tries a direct parse first (JSON mode), then scans for balanced ``{...}``
    spans and returns the last one that parses as an object.
    """
    text = (text or "").strip()
    if not text:
        return None
    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            return obj
    except Exception:
        pass
    for span in reversed(_balanced_objects(text)):
        try:
            obj = json.loads(span)
            if isinstance(obj, dict):
                return obj
        except Exception:
            continue
    return None


class LLMAgent:
    """One seat, backed by a chat model."""

    def __init__(
        self,
        seat: str,
        cfg: GameConfig,
        model_cfg: ModelConfig,
        client: LLMClient,
        persona_block: str = "",
        max_attempts: int = 3,
    ):
        self.seat = seat
        self.cfg = cfg
        self.model_cfg = model_cfg
        self.client = client
        self.persona_block = persona_block
        self.max_attempts = max_attempts
        self.call_log: List[dict] = []
        self.fallback_last = False

    # -- helpers ---------------------------------------------------------- #
    def _system(self, obs: Observation) -> str:
        return builder.build_system_prompt(
            self.cfg, self.seat, self.persona_block, obs.horizon_text
        )

    def _run(self, obs: Observation, phase: str, user_prompt: str, validate):
        """Call the model up to ``max_attempts`` times, validating the JSON.

        Returns (parsed_model_or_None, used_fallback). Records each attempt.
        """
        system = self._system(obs)
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user_prompt},
        ]
        error_note = ""
        for attempt in range(self.max_attempts):
            msgs = list(messages)
            if error_note:
                msgs.append({"role": "user", "content": error_note})
            result = self.client.chat(self.model_cfg, msgs)
            parsed = None
            err = result.error
            obj = extract_json(result.text)
            if obj is not None and err is None:
                try:
                    parsed = validate(obj)
                except ValidationError as ve:
                    err = f"schema validation failed: {ve.errors()[:3]}"
                except Exception as exc:
                    err = f"parse error: {exc}"
            elif err is None:
                err = "no JSON object found in response"

            self.call_log.append(
                {
                    "seat": self.seat,
                    "phase": phase,
                    "round": obs.round,
                    "attempt": attempt + 1,
                    "prompt_messages": msgs,
                    "raw_response": result.text,
                    "parsed_output": parsed.model_dump() if parsed is not None else None,
                    "latency_s": result.latency_s,
                    "prompt_tokens": result.prompt_tokens,
                    "completion_tokens": result.completion_tokens,
                    "total_tokens": result.total_tokens,
                    "retries": result.retries,
                    "error": err,
                    "model": result.model,
                }
            )
            if parsed is not None:
                return parsed, False
            error_note = (
                "Your previous response was invalid: "
                + (err or "unknown error")
                + ". Reply with ONLY the required JSON object."
            )
        return None, True

    # -- Agent interface -------------------------------------------------- #
    def message(self, obs: Observation) -> Optional[MessageOut]:
        if not self.cfg.messages_enabled:
            return None
        prompt = builder.build_message_prompt(obs, self.cfg)
        parsed, fb = self._run(obs, "message", prompt, lambda o: MessageOut(**o))
        self.fallback_last = fb
        if parsed is None:
            return None  # documented default: no message
        return parsed

    def contribute(self, obs: Observation) -> ContributionOut:
        prompt = builder.build_contribute_prompt(obs, self.cfg)
        parsed, fb = self._run(
            obs, "contribute", prompt, lambda o: ContributionOut(**o)
        )
        self.fallback_last = fb
        if parsed is None:
            return ContributionOut(
                contribution=0, reason="fallback: invalid output", predicted_others_mean=None
            )
        return parsed

    def reward(self, obs: Observation) -> RewardOut:
        prompt = builder.build_reward_prompt(obs, self.cfg)
        parsed, fb = self._run(obs, "reward", prompt, lambda o: RewardOut(**o))
        self.fallback_last = fb
        if parsed is None:
            return RewardOut(target=None, spend=0, reason="fallback: invalid output")
        return parsed

    def punish(self, obs: Observation) -> PunishOut:
        prompt = builder.build_punish_prompt(obs, self.cfg)
        parsed, fb = self._run(obs, "punish", prompt, lambda o: PunishOut(**o))
        self.fallback_last = fb
        if parsed is None:
            return PunishOut(target=None, spend=0, reason="fallback: invalid output")
        return parsed

    def intent_probe(self, obs: Observation) -> Optional[IntentProbeOut]:
        prompt = builder.build_intent_probe_prompt(obs, self.cfg)
        parsed, _ = self._run(
            obs, "intent_probe", prompt, lambda o: IntentProbeOut(**o)
        )
        return parsed

    def drain_calls(self) -> List[dict]:
        calls = self.call_log
        self.call_log = []
        return calls
