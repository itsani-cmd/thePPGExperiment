"""Build chat messages for each phase from an Observation.

Pure string assembly: reads the markdown templates once and formats them with
the public game state. Enforces the privacy rule — nothing here ever references
another seat's persona, principal, reasoning, or model.
"""

from __future__ import annotations

import os
from fractions import Fraction
from typing import Dict, List, Optional

from ..agents.base import Observation
from ..config import GameConfig
from .goal_wording import GOAL_WORDINGS

_PROMPT_DIR = os.path.dirname(__file__)
_PERSONAS_DIR = os.path.join(os.path.dirname(os.path.dirname(_PROMPT_DIR)), "personas")


def _read(name: str) -> str:
    with open(os.path.join(_PROMPT_DIR, name), "r", encoding="utf-8") as fh:
        return fh.read()


def horizon_text(cfg: GameConfig, disclose_final: bool, is_final: bool) -> str:
    """Condition-dependent horizon disclosure shown to agents."""
    if cfg.horizon.mode == "fixed":
        base = f"The game lasts exactly {cfg.horizon.rounds} rounds."
    else:
        base = (
            "The game may end after any round; its exact length is not disclosed. "
            "After each round there is a chance the game continues."
        )
    if disclose_final and is_final:
        extra = " This is the FINAL round: there are no future rounds"
        if not cfg.punishment_in_final_round:
            extra += " and no punishment phase this round."
        else:
            extra += "."
        base += extra
    return base


def _balances_block(obs: Observation, cfg: GameConfig) -> str:
    if not cfg.show_all_balances:
        return f"Your balance: {obs.own_balance} tokens."
    rows = [f"  {s}: {obs.balances[s]}" for s in obs.seat_labels]
    return "Current balances:\n" + "\n".join(rows)


def _history_block(obs: Observation) -> str:
    if not obs.history:
        return "No rounds have completed yet."
    lines: List[str] = []
    for r in obs.history:
        lines.append(f"Round {r.round}:")
        if r.messages:
            for m in r.messages:
                lines.append(f"  message {m.seat}: {m.text}")
        if r.contributions:
            contribs = ", ".join(
                f"{s}={r.contributions.get(s, 0)}" for s in obs.seat_labels
            )
            lines.append(f"  contributions: {contribs} (share each: {r.share})")
        if r.punishments:
            for p in r.punishments:
                lines.append(
                    "  punish {pr} -> {tg}: spend {sp}, damage {dm}".format(
                        pr=p.get("punisher"),
                        tg=p.get("target"),
                        sp=p.get("spend"),
                        dm=p.get("actual_damage"),
                    )
                )
        bals = ", ".join(
            f"{s}={r.balances_after_punishment.get(s, r.balances_after_distribution.get(s, 0))}"
            for s in obs.seat_labels
        )
        lines.append(f"  end-of-round balances: {bals}")
    return "\n".join(lines)


def _state_block(obs: Observation, cfg: GameConfig) -> str:
    return (
        f"You are {obs.seat}. Round {obs.round}.\n"
        + _balances_block(obs, cfg)
        + "\n\nHistory so far:\n"
        + _history_block(obs)
    )


def build_system_prompt(
    cfg: GameConfig,
    seat: str,
    persona_block: str,
    horizon_disclosure: str,
) -> str:
    tmpl = _read("system_base.md")
    mpcr = Fraction(cfg.multiplier).limit_denominator(1_000_000) / cfg.n_players
    messages_rule = (
        ": each player may post one public message." if cfg.messages_enabled
        else ": DISABLED this game (no messages)."
    )
    punishment_rule = (
        ": each player may spend tokens to reduce one other player's balance."
        if cfg.punishment_enabled
        else ": DISABLED this game (no punishment)."
    )
    sys = tmpl.format(
        seat=seat,
        n_players=cfg.n_players,
        seat_labels=", ".join(f"P{i+1}" for i in range(cfg.n_players)),
        goal_wording=GOAL_WORDINGS[cfg.goal_wording],
        start_tokens=cfg.start_tokens,
        horizon_text=horizon_disclosure,
        messages_rule=messages_rule,
        punishment_rule=punishment_rule,
        multiplier=cfg.multiplier,
        mpcr=f"{float(mpcr):.2f}",
    )
    if persona_block:
        sys = sys + "\n\n---\n" + persona_block
    return sys


def build_message_prompt(obs: Observation, cfg: GameConfig) -> str:
    tmpl = _read("decision_message.md")
    if obs.messages_this_round:
        spoken = "\n".join(f"  {m.seat}: {m.text}" for m in obs.messages_this_round)
        block = "Messages already posted this round:\n" + spoken
    else:
        block = "No one has posted a message yet this round."
    return tmpl.format(
        round=obs.round,
        state_block=_state_block(obs, cfg),
        message_phase_block=block,
        max_chars=cfg.message_max_chars,
    )


def build_contribute_prompt(obs: Observation, cfg: GameConfig) -> str:
    tmpl = _read("decision_contribute.md")
    if cfg.messages_enabled and obs.messages_this_round:
        spoken = "\n".join(f"  {m.seat}: {m.text}" for m in obs.messages_this_round)
        block = "Messages this round:\n" + spoken
    else:
        block = ""
    return tmpl.format(
        round=obs.round,
        state_block=_state_block(obs, cfg),
        messages_this_round_block=block,
        own_balance=obs.own_balance,
    )


def build_punish_prompt(obs: Observation, cfg: GameConfig) -> str:
    tmpl = _read("decision_punish.md")
    contribs = obs.this_round_contributions or {}
    dist = ", ".join(f"{s}={contribs.get(s, 0)}" for s in obs.seat_labels)
    block = (
        f"This round's contributions have been revealed: {dist} "
        f"(each player received a share of {obs.this_round_share})."
    )
    return tmpl.format(
        round=obs.round,
        state_block=_state_block(obs, cfg),
        distribution_block=block,
        max_spend=cfg.punish_max_spend,
        own_balance=obs.own_balance,
    )


def build_intent_probe_prompt(obs: Observation, cfg: GameConfig) -> str:
    tmpl = _read("decision_intent_probe.md")
    return tmpl.format(
        round=obs.round,
        state_block=_state_block(obs, cfg),
        deception_max=cfg.n_players - 1,
    )
