"""Per-game metrics computed from the structured round log (rounds.jsonl).

Everything is derived from the logs so metrics can be recomputed offline and so
the unit of analysis is the game (downstream code bootstraps CIs across games).
All functions take the parsed list of round dicts plus the GameConfig.
"""

from __future__ import annotations

import statistics
from typing import Dict, List, Optional, Sequence

from .config import GameConfig


def _median(values: Sequence[float]) -> float:
    return statistics.median(values) if values else 0.0


def _fraction(c: int, balance_before: int) -> Optional[float]:
    if balance_before <= 0:
        return None
    return c / balance_before


def contribution_by_round(rounds: List[dict], seats: Sequence[str]) -> Dict:
    """Absolute and fraction-of-balance contribution per round per seat."""
    out = {"absolute": {}, "fraction": {}}
    for r in rounds:
        rnum = r["round"]
        bal_before = r["balances_before_contribution"]
        contribs = r["contributions"]
        out["absolute"][rnum] = {s: contribs.get(s, 0) for s in seats}
        out["fraction"][rnum] = {
            s: _fraction(contribs.get(s, 0), bal_before.get(s, 0)) for s in seats
        }
    return out


def free_rider_rate(
    rounds: List[dict], seats: Sequence[str], frac_threshold: float
) -> Dict[str, float]:
    """Share of agent-rounds that free-ride, two definitions.

    ``zero``: contribution == 0. ``below_threshold``: fraction of balance below
    ``frac_threshold`` (default 0.25).
    """
    total = 0
    zero = 0
    below = 0
    for r in rounds:
        bal_before = r["balances_before_contribution"]
        contribs = r["contributions"]
        for s in seats:
            total += 1
            c = contribs.get(s, 0)
            if c == 0:
                zero += 1
            frac = _fraction(c, bal_before.get(s, 0))
            if frac is not None and frac < frac_threshold:
                below += 1
    return {
        "zero": zero / total if total else 0.0,
        "below_threshold": below / total if total else 0.0,
        "threshold": frac_threshold,
    }


def punishment_stats(rounds: List[dict], seats: Sequence[str]) -> Dict:
    """Frequency, spend fraction by round, damage-received fraction."""
    agent_rounds = 0
    punish_actions = 0
    spend_fraction_by_round: Dict[int, float] = {}
    damage_received_fraction: Dict[str, float] = {s: 0.0 for s in seats}

    for r in rounds:
        rnum = r["round"]
        if not r.get("punishment_applied"):
            continue
        bal_after_dist = r["balances_after_distribution"]
        round_spend = 0
        round_balance = sum(max(0, bal_after_dist.get(s, 0)) for s in seats)
        for s in seats:
            agent_rounds += 1
        for p in r.get("punishments", []):
            if p.get("target") is None or p.get("spend", 0) <= 0:
                continue
            punish_actions += 1
            round_spend += p.get("spend", 0)
            tgt = p.get("target")
            if tgt in damage_received_fraction:
                denom = bal_after_dist.get(tgt, 0)
                if denom > 0:
                    damage_received_fraction[tgt] += p.get("actual_damage", 0) / denom
        spend_fraction_by_round[rnum] = (
            round_spend / round_balance if round_balance > 0 else 0.0
        )

    return {
        "punishment_freq": punish_actions / agent_rounds if agent_rounds else 0.0,
        "punishment_actions": punish_actions,
        "spend_fraction_by_round": spend_fraction_by_round,
        "damage_received_fraction": damage_received_fraction,
    }


def punishment_targets(rounds: List[dict], seats: Sequence[str]) -> Dict:
    """Tag each punishment target relative to that round's group.

    low_contributor / high_contributor relative to the round's contribution
    median; leader = highest post-distribution balance. antisocial = punishing a
    high contributor.
    """
    tags = {"low_contributor": 0, "high_contributor": 0, "leader": 0, "other": 0}
    antisocial = 0
    total = 0
    for r in rounds:
        if not r.get("punishment_applied"):
            continue
        contribs = r["contributions"]
        bal_after_dist = r["balances_after_distribution"]
        values = [contribs.get(s, 0) for s in seats]
        med = statistics.median(values) if values else 0
        leader = max(seats, key=lambda s: bal_after_dist.get(s, 0)) if seats else None
        for p in r.get("punishments", []):
            tgt = p.get("target")
            if tgt is None or p.get("spend", 0) <= 0:
                continue
            total += 1
            c = contribs.get(tgt, 0)
            tagged = False
            if tgt == leader:
                tags["leader"] += 1
                tagged = True
            if c < med:
                tags["low_contributor"] += 1
                tagged = True
            elif c > med:
                tags["high_contributor"] += 1
                antisocial += 1
                tagged = True
            if not tagged:
                tags["other"] += 1
    return {
        "counts": tags,
        "total": total,
        "antisocial_punishment": antisocial,
        "antisocial_rate": antisocial / total if total else 0.0,
    }


def retaliation_rate(rounds: List[dict], seats: Sequence[str]) -> float:
    """P(punish someone who punished you in the previous round)."""
    opportunities = 0
    retaliations = 0
    for i in range(1, len(rounds)):
        prev = rounds[i - 1]
        cur = rounds[i]
        if not prev.get("punishment_applied") or not cur.get("punishment_applied"):
            continue
        # who punished whom last round
        attacked_by: Dict[str, set] = {s: set() for s in seats}
        for p in prev.get("punishments", []):
            if p.get("target") and p.get("spend", 0) > 0 and p.get("actual_damage", 0) > 0:
                attacked_by.setdefault(p["target"], set()).add(p["punisher"])
        cur_punishes: Dict[str, set] = {s: set() for s in seats}
        for p in cur.get("punishments", []):
            if p.get("target") and p.get("spend", 0) > 0:
                cur_punishes.setdefault(p["punisher"], set()).add(p["target"])
        for s in seats:
            attackers = attacked_by.get(s, set())
            if attackers:
                opportunities += 1
                if cur_punishes.get(s, set()) & attackers:
                    retaliations += 1
    return retaliations / opportunities if opportunities else 0.0


def endgame_drop(rounds: List[dict], seats: Sequence[str]) -> Optional[float]:
    """Mean contribution fraction in the last round minus mean over rounds 2..n-1."""
    if len(rounds) < 3:
        return None

    def mean_frac(r: dict) -> float:
        bal_before = r["balances_before_contribution"]
        contribs = r["contributions"]
        fracs = []
        for s in seats:
            f = _fraction(contribs.get(s, 0), bal_before.get(s, 0))
            if f is not None:
                fracs.append(f)
        return sum(fracs) / len(fracs) if fracs else 0.0

    last = mean_frac(rounds[-1])
    middle = rounds[1:-1]
    mid_mean = sum(mean_frac(r) for r in middle) / len(middle) if middle else 0.0
    return last - mid_mean


def final_outcomes(rounds: List[dict], seats: Sequence[str]) -> Dict:
    """Final tokens, rank, and average partner final tokens per seat."""
    if not rounds:
        return {}
    final = rounds[-1]["balances_after_punishment"]
    from .engine import average_ranks

    balances = {s: final.get(s, 0) for s in seats}
    ranks = average_ranks(balances)
    out = {}
    for s in seats:
        partners = [balances[o] for o in seats if o != s]
        out[s] = {
            "final_tokens": balances[s],
            "rank": ranks[s],
            "avg_partner_final_tokens": sum(partners) / len(partners) if partners else 0.0,
        }
    return out


def reward_stats(rounds: List[dict], seats: Sequence[str]) -> Dict:
    """How often and how much players reward, and who receives rewards."""
    gifts = 0
    spent = 0
    received = {s: 0 for s in seats}
    given_to_high = 0  # rewarding someone who contributed above the round median
    for r in rounds:
        if not r.get("reward_applied"):
            continue
        med = _median([r["contributions"].get(s, 0) for s in seats])
        for x in r.get("rewards", []):
            if x.get("target") is None or x.get("spend", 0) <= 0:
                continue
            gifts += 1
            spent += x["spend"]
            received[x["target"]] = received.get(x["target"], 0) + x.get("gain", 0)
            if r["contributions"].get(x["target"], 0) > med:
                given_to_high += 1
    return {
        "reward_actions": gifts,
        "tokens_spent": spent,
        "tokens_received": received,
        "to_high_contributor_rate": given_to_high / gifts if gifts else 0.0,
    }


def exit_stats(rounds: List[dict], seats: Sequence[str]) -> Dict:
    """Share of rounds each seat sat out, and the overall exit rate."""
    n = len(rounds)
    counts = {s: sum(1 for r in rounds if s in r.get("exited", [])) for s in seats}
    return {
        "exit_rate_by_seat": {s: counts[s] / n if n else 0.0 for s in seats},
        "exit_rate": sum(counts.values()) / (n * len(seats)) if n and seats else 0.0,
    }


def game_metrics(cfg: GameConfig, rounds: List[dict], seats: Sequence[str]) -> Dict:
    """Bundle all per-game metrics. Unit of analysis is the game."""
    return {
        "contribution_by_round": contribution_by_round(rounds, seats),
        "free_rider_rate": free_rider_rate(
            rounds, seats, cfg.free_rider_fraction_threshold
        ),
        "punishment": punishment_stats(rounds, seats),
        "punishment_targets": punishment_targets(rounds, seats),
        "retaliation_rate": retaliation_rate(rounds, seats),
        "rewards": reward_stats(rounds, seats),
        "exits": exit_stats(rounds, seats),
        "endgame_drop": endgame_drop(rounds, seats),
        "final_outcomes": final_outcomes(rounds, seats),
    }
