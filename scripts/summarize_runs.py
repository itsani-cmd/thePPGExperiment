#!/usr/bin/env python3
"""Print run-health, persona-fidelity and group-dynamics checks for saved games.

Examples::

    python scripts/summarize_runs.py                       # most recent run
    python scripts/summarize_runs.py runs/<run_id>         # every game in a run
    python scripts/summarize_runs.py runs/a runs/b         # pool several runs
    python scripts/summarize_runs.py runs/<run_id> --json  # machine-readable
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pgg.health import game_report  # noqa: E402

FALLBACK_WARN = 0.05


def _game_dirs(paths):
    dirs = []
    for p in paths:
        if os.path.exists(os.path.join(p, "rounds.jsonl")):
            dirs.append(p)
        else:
            dirs += sorted(os.path.dirname(f) for f in glob.glob(os.path.join(p, "*", "rounds.jsonl")))
    return dirs


def _latest_run(root="runs"):
    files = glob.glob(os.path.join(root, "*", "*", "rounds.jsonl"))
    if not files:
        sys.exit("No games found under runs/. Run a game first.")
    return os.path.dirname(os.path.dirname(max(files, key=os.path.getmtime)))


def _f(x, nd=2):
    return "-" if x is None else f"{x:.{nd}f}"


def _mean(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("paths", nargs="*")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    dirs = _game_dirs(args.paths or [_latest_run()])
    if not dirs:
        sys.exit("No games found in the given paths.")
    reports = [game_report(d) for d in dirs]
    if args.json:
        print(json.dumps(reports, indent=2, default=str))
        return 0

    print(f"{len(reports)} game(s)\n")
    print("1. RUN HEALTH")
    print(f"{'game':<34}{'done':<6}{'fallback':<10}{'call err':<10}{'429s':<6}{'retries':<9}{'lat mean/max s':<16}{'tokens':<9}")
    for r in reports:
        h = r["health"]
        flag = "  <-- many fallbacks" if h["fallback_rate"] > FALLBACK_WARN else ""
        print(
            f"{r['game'][-32:]:<34}{str(h['finished']):<6}{_f(h['fallback_rate'], 3):<10}"
            f"{_f(h['call_error_rate'], 3):<10}{h['rate_limit_errors']:<6}{h['extra_retries']:<9}"
            f"{_f(h['latency_mean_s'], 1) + '/' + _f(h['latency_max_s'], 1):<16}{h['total_tokens']:<9}{flag}"
        )
    if any(r["health"]["possible_persona_leaks"] or r["health"]["truncated_messages"] for r in reports):
        print(
            f"  truncated messages: {sum(r['health']['truncated_messages'] for r in reports)}, "
            f"possible persona leaks: {sum(r['health']['possible_persona_leaks'] for r in reports)}"
        )

    print("\n2. PERSONA FIDELITY (pooled over games; one row per persona)")
    pooled = defaultdict(lambda: defaultdict(list))
    for r in reports:
        for p in r["personas"].values():
            for k, v in p.items():
                if k != "persona":
                    pooled[p["persona"]][k].append(v)
    cols = [
        ("mean_fraction", "mean contrib"),
        ("std_fraction", "round-to-round sd"),
        ("zero_rate", "zero rate"),
        ("punish_per_round", "punish/round"),
        ("reward_per_round", "reward/round"),
        ("exit_rate", "exit rate"),
        ("tracks_others_corr", "corr w/ others t-1"),
        ("final_tokens", "final tokens"),
    ]
    print(f"{'persona':<16}" + "".join(f"{c[1]:<20}" for c in cols))
    for persona, d in sorted(pooled.items(), key=lambda kv: -(_mean(kv[1]["mean_fraction"]) or 0)):
        print(f"{persona:<16}" + "".join(f"{_f(_mean(d[k])):<20}" for k, _ in cols))
    print("  expect: good_samaritan > socialist > follower > flaky > selfish on mean contrib;")
    print("  flaky highest sd; follower corr w/ others clearly positive; selfish high zero rate.")

    print("\n3. GROUP DYNAMICS (mean over games)")
    dyn = [r["dynamics"] for r in reports if r["dynamics"]]
    if not dyn:
        print("  (no completed rounds in the selected games)")
        return 0
    for key, label in [
        ("cooperation_slope", "cooperation slope (fraction/round)"),
        ("efficiency", "efficiency (0 = nobody gained, 1 = full cooperation)"),
        ("gini_final", "final Gini"),
        ("tokens_destroyed_by_punishment", "tokens destroyed by punishment"),
        ("next_round_change_if_punished", "next-round contrib change if punished"),
        ("next_round_change_if_not", "next-round contrib change if not"),
        ("converged_round", "round where contributions settle"),
    ]:
        print(f"  {label:<58}{_f(_mean([d[key] for d in dyn]))}")
    print("  contribution by round (mean over games):")
    width = max(len(d["mean_fraction_by_round"]) for d in dyn)
    row = [_mean([d["mean_fraction_by_round"][i] for d in dyn if i < len(d["mean_fraction_by_round"])]) for i in range(width)]
    print("   ", " ".join(_f(x) for x in row))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
