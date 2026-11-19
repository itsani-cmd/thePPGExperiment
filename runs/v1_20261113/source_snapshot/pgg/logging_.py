"""Append-only JSONL writers for one game directory.

Layout (build spec §7)::

    runs/<run_id>/<game_id>/
        config.json     full resolved config, seed, git hash, timestamps
        rounds.jsonl    one line per round
        calls.jsonl     one line per LLM call
        summary.json    final balances, ranks, totals, metrics

Each round and each call is flushed immediately so a crash can resume from the
last complete round. API keys are never written (the client holds them, and we
only ever serialize ModelConfig which has no key field).
"""

from __future__ import annotations

import dataclasses
import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


def _default(o: Any):
    if dataclasses.is_dataclass(o):
        return dataclasses.asdict(o)
    if hasattr(o, "model_dump"):
        return o.model_dump()
    if isinstance(o, (set, tuple)):
        return list(o)
    return str(o)


def _dumps(obj: Any) -> str:
    return json.dumps(obj, default=_default, ensure_ascii=False, sort_keys=True)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class GameLogger:
    def __init__(self, run_dir: str, game_id: str):
        self.dir = os.path.join(run_dir, game_id)
        os.makedirs(self.dir, exist_ok=True)
        self.rounds_path = os.path.join(self.dir, "rounds.jsonl")
        self.calls_path = os.path.join(self.dir, "calls.jsonl")
        self.config_path = os.path.join(self.dir, "config.json")
        self.summary_path = os.path.join(self.dir, "summary.json")

    # -- config ----------------------------------------------------------- #
    def write_config(self, config_obj: Dict[str, Any]) -> None:
        payload = dict(config_obj)
        payload.setdefault("written_at", now_iso())
        with open(self.config_path, "w", encoding="utf-8") as fh:
            fh.write(_dumps(payload))

    # -- rounds ----------------------------------------------------------- #
    def append_round(self, record: Dict[str, Any]) -> None:
        with open(self.rounds_path, "a", encoding="utf-8") as fh:
            fh.write(_dumps(record) + "\n")
            fh.flush()
            os.fsync(fh.fileno())

    def completed_rounds(self) -> int:
        """Number of rounds already logged (for resume)."""
        if not os.path.exists(self.rounds_path):
            return 0
        count = 0
        with open(self.rounds_path, "r", encoding="utf-8") as fh:
            for line in fh:
                if line.strip():
                    count += 1
        return count

    def read_rounds(self) -> List[Dict[str, Any]]:
        if not os.path.exists(self.rounds_path):
            return []
        out = []
        with open(self.rounds_path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    out.append(json.loads(line))
        return out

    # -- calls ------------------------------------------------------------ #
    def append_calls(self, calls: List[Dict[str, Any]]) -> None:
        if not calls:
            return
        with open(self.calls_path, "a", encoding="utf-8") as fh:
            for c in calls:
                fh.write(_dumps(c) + "\n")
            fh.flush()
            os.fsync(fh.fileno())

    # -- summary ---------------------------------------------------------- #
    def write_summary(self, summary: Dict[str, Any]) -> None:
        with open(self.summary_path, "w", encoding="utf-8") as fh:
            fh.write(_dumps(summary))

    def is_complete(self) -> bool:
        return os.path.exists(self.summary_path)


def git_hash(cwd: Optional[str] = None) -> Optional[str]:
    import subprocess

    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=cwd,
            stderr=subprocess.DEVNULL,
        )
        return out.decode().strip()
    except Exception:
        return None
