#!/usr/bin/env python3
"""CLI to run a batch of PGG games.

Examples
--------
Offline, no API key::

    python scripts/run_batch.py --config configs/baseline.yaml --agents mock --games 20

Real run against an OpenAI-compatible proxy (needs PGG_BASE_URL / PGG_API_KEY)::

    python scripts/run_batch.py --config configs/baseline.yaml --agents llm --games 5

Estimate call volume without running::

    python scripts/run_batch.py --config configs/baseline.yaml --dry-run

Resume an interrupted run::

    python scripts/run_batch.py --config configs/baseline.yaml --agents mock --resume runs/abc
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time

# allow running from the repo root without installing
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pgg import transcript  # noqa: E402
from pgg.config import load_run_config  # noqa: E402
from pgg.llm.client import LLMClient  # noqa: E402
from pgg.runner import count_calls, run_batch  # noqa: E402


def _parse_args(argv=None):
    p = argparse.ArgumentParser(description="Run a batch of PGG-Bench games.")
    p.add_argument("--config", required=True, help="path to a YAML config")
    p.add_argument(
        "--agents", choices=["mock", "llm"], default="mock", help="agent backend"
    )
    p.add_argument("--games", type=int, default=None, help="override number of games")
    p.add_argument(
        "--mock-type",
        default="cooperate",
        help="mock agent type when seats don't set agent_type "
        "(cooperate|defect|titfortat|random)",
    )
    p.add_argument("--run-id", default=None, help="run directory name (default: timestamp)")
    p.add_argument("--runs-root", default="runs", help="root directory for runs")
    p.add_argument("--resume", default=None, help="resume this run_id, skipping finished games")
    p.add_argument("--game-workers", type=int, default=1, help="parallel games")
    p.add_argument("--phase-workers", type=int, default=5, help="parallel agent calls per phase")
    p.add_argument("--dry-run", action="store_true", help="print call-count estimate and exit")
    p.add_argument(
        "--live",
        action="store_true",
        help="print each round (messages, contributions, punishments) as it finishes",
    )
    p.add_argument("--timeout", type=float, default=60.0, help="per-call timeout seconds")
    return p.parse_args(argv)


def _apply_mock_type(run, mock_type):
    """Fill agent_type on seats that don't specify one (mock runs only)."""
    for seat in run.seats:
        if seat.agent_type is None:
            seat.agent_type = mock_type


def _verify_models(run, client: LLMClient):
    served = set(client.list_models())
    if not served:
        print(
            "WARNING: could not list models from the endpoint; skipping verification.",
            file=sys.stderr,
        )
        return
    used = {s.model for s in run.seats if s.model} or set(run.models)
    if run.sweep_models:
        used = set(run.sweep_models)
    missing = [run.models[k].model for k in used if run.models[k].model not in served]
    if missing:
        print(
            "ERROR: configured models not served by the endpoint: "
            + ", ".join(sorted(set(missing))),
            file=sys.stderr,
        )
        sys.exit(2)


def _live_printer(kind, data):
    if kind == "start":
        print(transcript.format_header(data["game_id"], data["who"], data["total_rounds"]), flush=True)
    elif kind == "progress":
        print(f"\n... {data['text']}", flush=True)
    elif kind == "round":
        print(transcript.format_round(data["round"], data["who"]), flush=True)
    elif kind == "end":
        print(transcript.format_summary(data["summary"], data["who"]), flush=True)


def main(argv=None):
    args = _parse_args(argv)
    run = load_run_config(args.config)

    if args.dry_run:
        est = count_calls(run, games=args.games)
        print(json.dumps(est, indent=2))
        return 0

    if args.agents == "mock":
        _apply_mock_type(run, args.mock_type)

    client = None
    if args.agents == "llm":
        client = LLMClient(timeout_s=args.timeout)
        _verify_models(run, client)

    base_id = args.resume or args.run_id or f"{run.name}_{int(time.time())}"
    sweep = run.sweep_models or [None]
    for model_key in sweep:
        this_run = run.model_copy(deep=True)
        run_id = base_id
        if model_key:
            for seat in this_run.seats:
                seat.model = model_key
            run_id = f"{base_id}_{model_key}"
            print(f"=== model: {model_key} ({this_run.models[model_key].model}) ===")
        run_dir = os.path.join(args.runs_root, run_id)

        summaries = run_batch(
            this_run,
            run_dir=run_dir,
            agent_kind=args.agents,
            games=args.games,
            client=client,
            game_workers=args.game_workers,
            phase_workers=args.phase_workers,
            resume=bool(args.resume),
            on_event=_live_printer if args.live else None,
        )

        print(f"Completed {len(summaries)} game(s). Logs in {run_dir}")
        if summaries:
            tokens = [s["total_tokens"] for s in summaries]
            print(f"  total tokens per game: min={min(tokens)} max={max(tokens)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
