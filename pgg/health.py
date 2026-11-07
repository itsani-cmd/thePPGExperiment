"""Run-health, persona-fidelity and group-dynamics checks for saved games.

Reads the files in one game folder (rounds.jsonl, config.json, and calls.jsonl for
real-model runs) and returns plain dicts. ``scripts/summarize_runs.py`` prints them.
Unlike ``metrics.py`` these are not written into summary.json; they are computed on
demand from the logs, so they can change without invalidating old runs.
"""

from __future__ import annotations

import json
import os
import statistics
from typing import Dict, List, Optional, Sequence

LEAK_WORDS = ("my principal", "my brief", "my instructions", "persona", "i was told to")
RATE_LIMIT_WORDS = ("429", "rate limit", "rate_limit", "quota")


def _read_jsonl(path: str) -> List[dict]:
    if not os.path.exists(path):
        return []
    with open(path) as f:
        return [json.loads(line) for line in f if line.strip()]


def load_game(game_dir: str) -> Dict:
    with open(os.path.join(game_dir, "config.json")) as f:
        cfg = json.load(f)
    return {
        "dir": game_dir,
        "config": cfg,
        "rounds": _read_jsonl(os.path.join(game_dir, "rounds.jsonl")),
        "calls": _read_jsonl(os.path.join(game_dir, "calls.jsonl")),
        "finished": os.path.exists(os.path.join(game_dir, "summary.json")),
        "persona_of": {
            s["seat"]: s.get("persona") or "none" for s in cfg["seat_assignment"]
        },
    }


def _mean(xs: Sequence[float]) -> Optional[float]:
    return sum(xs) / len(xs) if xs else None


def _std(xs: Sequence[float]) -> Optional[float]:
    return statistics.pstdev(xs) if len(xs) > 1 else None


def _pearson(xs: Sequence[float], ys: Sequence[float]) -> Optional[float]:
    if len(xs) < 3:
        return None
    mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
    sx = sum((x - mx) ** 2 for x in xs)
    sy = sum((y - my) ** 2 for y in ys)
    if sx == 0 or sy == 0:
        return None
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / (sx * sy) ** 0.5


def _slope(ys: Sequence[float]) -> Optional[float]:
    """Least-squares slope of ys against 0..n-1."""
    n = len(ys)
    if n < 2:
        return None
    mx, my = (n - 1) / 2, sum(ys) / n
    return sum((i - mx) * (y - my) for i, y in enumerate(ys)) / sum(
        (i - mx) ** 2 for i in range(n)
    )


def _fracs(rounds: List[dict], seat: str) -> List[Optional[float]]:
    out = []
    for r in rounds:
        bal = r["balances_before_contribution"].get(seat, 0)
        out.append(r["contributions"].get(seat, 0) / bal if bal > 0 else None)
    return out


# --------------------------------------------------------------------------- #
# 1. Run health
# --------------------------------------------------------------------------- #
def run_health(g: Dict) -> Dict:
    rounds, calls = g["rounds"], g["calls"]
    seats = list(g["persona_of"])
    fb = {s: 0 for s in seats}
    decisions = {s: 0 for s in seats}
    truncated = 0
    leaks = 0
    for r in rounds:
        for s in seats:
            decisions[s] += 1
            fb[s] += bool(r["contribution_fallbacks"].get(s))
        for p in r["punishments"]:
            decisions[p["punisher"]] += 1
            fb[p["punisher"]] += bool(p["fallback_used"])
        for m in r["messages"]:
            decisions[m["seat"]] += 1
            fb[m["seat"]] += bool(m["fallback_used"])
            truncated += bool(m.get("truncated"))
            leaks += any(w in m["text"].lower() for w in LEAK_WORDS)
    total_dec = sum(decisions.values())
    errors = [c for c in calls if c.get("error")]
    lat = [c["latency_s"] for c in calls if c.get("latency_s")]
    by_phase: Dict[str, Dict[str, float]] = {}
    for c in calls:
        p = by_phase.setdefault(c["phase"], {"calls": 0, "tokens": 0})
        p["calls"] += 1
        p["tokens"] += c.get("total_tokens") or 0
    return {
        "finished": g["finished"],
        "rounds_played": len(rounds),
        "fallback_rate": sum(fb.values()) / total_dec if total_dec else 0.0,
        "fallback_rate_by_seat": {
            s: fb[s] / decisions[s] if decisions[s] else 0.0 for s in seats
        },
        "calls": len(calls),
        "call_error_rate": len(errors) / len(calls) if calls else None,
        "rate_limit_errors": sum(
            any(w in str(c["error"]).lower() for w in RATE_LIMIT_WORDS) for c in errors
        ),
        "extra_retries": sum(c.get("retries") or 0 for c in calls),
        "latency_mean_s": _mean(lat),
        "latency_max_s": max(lat) if lat else None,
        "total_tokens": sum(p["tokens"] for p in by_phase.values()),
        "by_phase": by_phase,
        "truncated_messages": truncated,
        "possible_persona_leaks": leaks,
    }


# --------------------------------------------------------------------------- #
# 2. Persona fidelity
# --------------------------------------------------------------------------- #
def persona_fidelity(g: Dict) -> Dict[str, Dict]:
    """Per persona: how it actually behaved. One entry per persona in this game."""
    rounds = g["rounds"]
    out: Dict[str, Dict] = {}
    for seat, persona in g["persona_of"].items():
        fr = _fracs(rounds, seat)
        vals = [f for f in fr if f is not None]
        punish_rounds = [r for r in rounds if r.get("punishment_applied")]
        acts = sum(
            1
            for r in punish_rounds
            for p in r["punishments"]
            if p["punisher"] == seat and p["target"] and p["spend"] > 0
        )
        # follower check: own contribution vs the others' mean last round
        own, others_prev = [], []
        for i in range(1, len(rounds)):
            if fr[i] is None:
                continue
            prev = [
                f
                for o, f in ((o, _fracs(rounds[i - 1 : i], o)[0]) for o in g["persona_of"])
                if o != seat and f is not None
            ]
            if prev:
                own.append(fr[i])
                others_prev.append(sum(prev) / len(prev))
        out[seat] = {
            "persona": persona,
            "mean_fraction": _mean(vals),
            "std_fraction": _std(vals),
            "zero_rate": _mean([float(r["contributions"].get(seat, 0) == 0) for r in rounds]),
            "punish_per_round": acts / len(punish_rounds) if punish_rounds else None,
            "exit_rate": _mean([float(seat in r.get("exited", [])) for r in rounds]),
            "tracks_others_corr": _pearson(others_prev, own),
            "final_tokens": rounds[-1]["balances_after_punishment"].get(seat) if rounds else None,
        }
    return out


# --------------------------------------------------------------------------- #
# 3. Group dynamics
# --------------------------------------------------------------------------- #
def _gini(xs: Sequence[float]) -> Optional[float]:
    xs = sorted(max(0, x) for x in xs)
    total = sum(xs)
    if not xs or total == 0:
        return None
    n = len(xs)
    return sum((2 * (i + 1) - n - 1) * x for i, x in enumerate(xs)) / (n * total)


def group_dynamics(g: Dict, converge_band: float = 0.1) -> Dict:
    rounds = g["rounds"]
    cfg = g["config"]["game_config"]
    seats = list(g["persona_of"])
    if not rounds:
        return {}
    n, start, mult = len(seats), cfg["start_tokens"], cfg["multiplier"]
    mean_frac = []
    spread = []
    for r in rounds:
        fs = [
            r["contributions"].get(s, 0) / r["balances_before_contribution"][s]
            for s in seats
            if r["balances_before_contribution"].get(s, 0) > 0
        ]
        mean_frac.append(_mean(fs))
        spread.append(_std(fs))
    final = rounds[-1]["balances_after_punishment"]
    total_final = sum(final.get(s, 0) for s in seats)
    # Cooperative ceiling: everyone puts in everything every round, no punishment.
    ceiling = n * start * mult ** len(rounds)
    efficiency = (total_final - n * start) / (ceiling - n * start) if ceiling > n * start else None

    destroyed = 0
    for r in rounds:
        if r.get("punishment_applied"):
            destroyed += sum(r["balances_after_distribution"].values()) - sum(
                r["balances_after_punishment"].values()
            )
    # Does being punished change next-round contribution, relative to everyone else?
    deltas_hit, deltas_other = [], []
    for i in range(len(rounds) - 1):
        hit = {
            p["target"]
            for p in rounds[i]["punishments"]
            if p["target"] and p["actual_damage"] > 0
        }
        for s in seats:
            a = _fracs(rounds[i : i + 1], s)[0]
            b = _fracs(rounds[i + 1 : i + 2], s)[0]
            if a is None or b is None:
                continue
            (deltas_hit if s in hit else deltas_other).append(b - a)

    converged = None
    for i in range(len(rounds)):
        tail = [m for m in mean_frac[i:] if m is not None]
        if tail and all(abs(m - tail[0]) <= converge_band for m in tail) and len(tail) >= 3:
            converged = rounds[i]["round"]
            break
    return {
        "mean_fraction_by_round": mean_frac,
        "cooperation_slope": _slope([m for m in mean_frac if m is not None]),
        "spread_by_round": spread,
        "converged_round": converged,
        "efficiency": efficiency,
        "gini_final": _gini([final.get(s, 0) for s in seats]),
        "tokens_destroyed_by_punishment": destroyed,
        "next_round_change_if_punished": _mean(deltas_hit),
        "next_round_change_if_not": _mean(deltas_other),
        "n_punished_observations": len(deltas_hit),
    }


def game_report(game_dir: str) -> Dict:
    g = load_game(game_dir)
    return {
        "game": game_dir,
        "health": run_health(g),
        "personas": persona_fidelity(g),
        "dynamics": group_dynamics(g),
    }
