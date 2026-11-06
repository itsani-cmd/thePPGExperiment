"""Human-readable transcript of a game, built from rounds.jsonl records.

Used by ``run_batch.py --live`` (print each round as it finishes) and by
``scripts/show_game.py`` (replay a saved game).
"""

from __future__ import annotations

import json
import os
from typing import Dict, List


def _label(seat: str, who: Dict[str, str]) -> str:
    persona = who.get(seat)
    return f"{seat} ({persona})" if persona else seat


def format_round(r: dict, who: Dict[str, str]) -> str:
    seats = sorted(r["contributions"].keys())
    lines: List[str] = [f"\n=== Round {r['round']} ==="]

    if r.get("messages"):
        lines.append("Messages:")
        for m in r["messages"]:
            flag = " [truncated]" if m.get("truncated") else ""
            lines.append(f"  {_label(m['seat'], who)}: {m['text']}{flag}")

    lines.append("Contributions:")
    for s in seats:
        before = r["balances_before_contribution"].get(s, 0)
        c = r["contributions"][s]
        fb = "  [fallback]" if r.get("contribution_fallbacks", {}).get(s) else ""
        lines.append(f"  {_label(s, who):28s} gave {c:>3} of {before}{fb}")
    lines.append(
        f"  pot {r['pot']}, each player gets {r['share']}, carry {r['carry_out']}"
    )

    acts = [p for p in r.get("punishments", []) if p.get("target") and p.get("spend", 0) > 0]
    if not r.get("punishment_applied", True):
        lines.append("Punishment: skipped this round")
    elif acts:
        lines.append("Punishment:")
        for p in acts:
            lines.append(
                f"  {_label(p['punisher'], who)} -> {_label(p['target'], who)}: "
                f"spent {p['cost']}, removed {p['actual_damage']}"
            )
            if p.get("reason"):
                lines.append(f"      why: {p['reason']}")
    else:
        lines.append("Punishment: nobody punished")

    end = r["balances_after_punishment"]
    lines.append("Balances: " + ", ".join(f"{s}={end[s]}" for s in seats))
    return "\n".join(lines)


def format_header(game_id: str, who: Dict[str, str], total_rounds: int) -> str:
    seats = ", ".join(_label(s, who) for s in sorted(who))
    return f"\n##### {game_id}: {total_rounds} rounds #####\nSeats: {seats}"


def format_summary(summary: dict, who: Dict[str, str]) -> str:
    lines = ["\n=== Final result ==="]
    scores = summary["scores"]
    for s in sorted(scores, key=lambda k: scores[k]["rank"]):
        lines.append(
            f"  rank {scores[s]['rank']:>3}  {_label(s, who):28s} {scores[s]['final_tokens']} tokens"
        )
    return "\n".join(lines)


def load_who(game_dir: str) -> Dict[str, str]:
    with open(os.path.join(game_dir, "config.json"), encoding="utf-8") as fh:
        cfg = json.load(fh)
    return {
        s["seat"]: (s.get("persona") or s.get("principal") or s.get("agent_type") or "")
        for s in cfg["seat_assignment"]
    }


def format_game(game_dir: str) -> str:
    who = load_who(game_dir)
    with open(os.path.join(game_dir, "config.json"), encoding="utf-8") as fh:
        total = json.load(fh).get("sampled_total_rounds", "?")
    out = [format_header(os.path.basename(game_dir.rstrip("/")), who, total)]
    with open(os.path.join(game_dir, "rounds.jsonl"), encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                out.append(format_round(json.loads(line), who))
    summary_path = os.path.join(game_dir, "summary.json")
    if os.path.exists(summary_path):
        with open(summary_path, encoding="utf-8") as fh:
            out.append(format_summary(json.load(fh), who))
    else:
        out.append("\n(game not finished)")
    return "\n".join(out)
