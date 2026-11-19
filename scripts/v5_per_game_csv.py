#!/usr/bin/env python3
"""Write one CSV row per V5 game (2 models x 4 arms x 10 games).

Reads the run folders runs/v5_<arm>_<model>/game_* (gitignored, so you need the
raw logs locally) and writes group metrics plus per-persona contribution share
and final tokens::

    python scripts/v5_per_game_csv.py docs/V5_per_game_stats.csv

Rates are 0-1. free_rider_rate = share of player-rounds giving < 25% of balance;
punishment_freq = share of player-rounds with a punishment; retaliation_rate =
how often a punished player punishes its punisher in the next round;
share_given_<persona> = total given / total balance before giving.
"""

from __future__ import annotations

import csv
import glob
import json
import os
import sys

# allow running from the repo root without installing
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pgg import metrics  # noqa: E402

SEATS = ["P1", "P2", "P3", "P4", "P5"]
PERSONAS = ["good_samaritan", "socialist", "follower", "flaky", "selfish"]
# run-folder arm -> (label, contributions_visible, punishments_visible)
ARMS = {
    "named": ("Named", "named", "public"),
    "anon_private": ("A_private", "anonymous", "private"),
    "anon_public": ("B_public", "anonymous", "public"),
    "anon_hidden": ("C_hidden", "anonymous", "hidden"),
}
# run-folder model key -> model name
MODELS = {"sonnet": "claude-sonnet-5-5", "chatgpt": "gpt-6-luna"}
SEED = 1234  # game k uses seed SEED + k

COLUMNS = [
    "variation", "model", "arm", "contributions_visible", "punishments_visible",
    "game", "seed", "rounds", "free_rider_rate", "punishment_freq",
    "retaliation_rate", "final_group_total", "top_finisher",
] + [f"share_given_{p}" for p in PERSONAS] + [f"final_tokens_{p}" for p in PERSONAS]


def _personas(config: dict) -> dict:
    sa = config["seat_assignment"]
    if isinstance(sa, dict):
        return {s: (v["persona"] if isinstance(v, dict) else v) for s, v in sa.items()}
    return {x["seat"]: x["persona"] for x in sa}


def game_row(game_dir: str, model: str, arm: tuple) -> dict:
    label, cv, pv = arm
    with open(os.path.join(game_dir, "rounds.jsonl")) as f:
        rounds = [json.loads(line) for line in f]
    with open(os.path.join(game_dir, "config.json")) as f:
        persona = _personas(json.load(f))
    with open(os.path.join(game_dir, "summary.json")) as f:
        final = json.load(f)["final_balances"]
    k = int(game_dir.rsplit("_", 1)[1])
    row = {
        "variation": "V5", "model": model, "arm": label,
        "contributions_visible": cv, "punishments_visible": pv,
        "game": k, "seed": SEED + k, "rounds": len(rounds),
        "free_rider_rate": round(metrics.free_rider_rate(rounds, SEATS, 0.25)["below_threshold"], 4),
        "punishment_freq": round(metrics.punishment_stats(rounds, SEATS)["punishment_freq"], 4),
        "retaliation_rate": round(metrics.retaliation_rate(rounds, SEATS), 4),
        "final_group_total": sum(final.values()),
        "top_finisher": persona[max(final, key=final.get)],
    }
    for s in SEATS:
        live = [r for r in rounds if r["balances_before_contribution"][s] > 0]
        given = sum(r["contributions"][s] for r in live)
        balance = sum(r["balances_before_contribution"][s] for r in live)
        row[f"share_given_{persona[s]}"] = round(given / balance, 4) if balance else 0
        row[f"final_tokens_{persona[s]}"] = final[s]
    return row


def main(argv=None) -> None:
    out = (argv or sys.argv[1:] or ["docs/V5_per_game_stats.csv"])[0]
    with open(out, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader()
        n = 0
        for key, model in MODELS.items():
            for arm_dir, arm in ARMS.items():
                for game_dir in sorted(glob.glob(f"runs/v5_{arm_dir}_{key}/game_*")):
                    writer.writerow(game_row(game_dir, model, arm))
                    n += 1
    print(f"wrote {n} games to {out}")


if __name__ == "__main__":
    main()
