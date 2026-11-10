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
        skipped = []
        if cfg.reward_enabled and not cfg.reward_in_final_round:
            skipped.append("reward")
        if cfg.punishment_enabled and not cfg.punishment_in_final_round:
            skipped.append("punishment")
        if skipped:
            extra += f" and no {' or '.join(skipped)} phase this round."
        else:
            extra += "."
        base += extra
    return base


def _balances_block(obs: Observation, cfg: GameConfig) -> str:
    if not cfg.balances_visible:
        return f"Your balance: {obs.own_balance} tokens."
    rows = [f"  {s}: {obs.balances[s]}" for s in obs.seat_labels]
    return "Current balances:\n" + "\n".join(rows)


def _history_block(obs: Observation, cfg: GameConfig) -> str:
    anon = cfg.contributions_visible == "anonymous"
    if not obs.history:
        return "No rounds have completed yet."
    lines: List[str] = []
    for r in obs.history:
        lines.append(f"Round {r.round}:")
        if r.messages:
            for m in r.messages:
                lines.append(f"  message {m.seat}: {m.text}")
        if r.contributions and anon:
            lines.append(
                f"  you contributed {r.contributions.get(obs.seat, 0)}; group total "
                f"{r.total_contributed} (share each: {r.share})"
            )
        elif r.contributions:
            contribs = ", ".join(
                f"{s}={r.contributions.get(s, 0)}" for s in obs.seat_labels
            )
            lines.append(f"  contributions: {contribs} (share each: {r.share})")
        if r.exited:
            lines.append(f"  sat out (exit): {', '.join(r.exited)}")
        for rw in r.rewards:
            lines.append(
                "  reward {g} -> {t}: spend {sp}, gain {gn}".format(
                    g=rw.get("giver"), t=rw.get("target"), sp=rw.get("spend"), gn=rw.get("gain")
                )
            )
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
        if anon:
            own = r.balances_after_punishment.get(obs.seat, 0)
            lines.append(f"  your end-of-round balance: {own}")
        else:
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
        + _history_block(obs, cfg)
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
    exit_rule = (
        f" Instead of contributing you may EXIT the round: you keep your tokens, get a fixed "
        f"{cfg.exit_payoff} extra token(s), and take no part in that round's fund, rewards or "
        f"punishment. If anyone exits, the fund is split equally among the players who did not exit."
        if cfg.exit_enabled
        else ""
    )
    reveal_rule = (
        "Contributions stay anonymous: each player learns only their own contribution, "
        "the group total, and the per-player share. Other players' balances are also hidden."
        if cfg.contributions_visible == "anonymous"
        else "Everyone's contribution and the per-player share are then revealed."
    )
    reward_phase = (
        "  4. Reward: each player may spend tokens to give tokens to one other player "
        f"(each token spent gives them {cfg.reward_ratio}).\n"
        if cfg.reward_enabled
        else ""
    )
    split_text = (
        f"the players who did not exit (out of {cfg.n_players})"
        if cfg.exit_enabled
        else f"all {cfg.n_players} players"
    )
    sys = tmpl.format(
        split_text=split_text,
        exit_rule=exit_rule,
        reveal_rule=reveal_rule,
        reward_phase=reward_phase,
        punish_num=5 if cfg.reward_enabled else 4,
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
    secrecy = (
        "Contributions are secret, and stay anonymous even after the round."
        if cfg.contributions_visible == "anonymous"
        else "Contributions are secret until after the round."
    )
    exit_field = ', "exit": <true to sit this round out instead, else false>' if cfg.exit_enabled else ""
    if cfg.exit_enabled:
        block = (block + "\n\n" if block else "") + (
            f"You may instead EXIT this round (set exit to true and contribution to 0; contribution is then ignored). "
            f"You would keep your {obs.own_balance} tokens and get {cfg.exit_payoff} extra, "
            f"but receive no share and cannot reward or punish."
        )
    return tmpl.format(
        round=obs.round,
        state_block=_state_block(obs, cfg),
        messages_this_round_block=block,
        own_balance=obs.own_balance,
        secrecy_rule=secrecy,
        exit_field=exit_field,
    )


def _distribution_block(obs: Observation, cfg: GameConfig) -> str:
    contribs = obs.this_round_contributions or {}
    if cfg.contributions_visible == "anonymous":
        block = (
            f"This round you contributed {contribs.get(obs.seat, 0)} and the group contributed "
            f"{obs.this_round_total} in total; individual contributions are not revealed "
            f"(each player in the round received a share of {obs.this_round_share})."
        )
    else:
        dist = ", ".join(f"{s}={contribs.get(s, 0)}" for s in obs.seat_labels)
        block = (
            f"This round's contributions have been revealed: {dist} "
            f"(each player received a share of {obs.this_round_share})."
        )
    if obs.this_round_exited:
        block += f" Sat out this round: {', '.join(obs.this_round_exited)}."
    return block


def build_reward_prompt(obs: Observation, cfg: GameConfig) -> str:
    tmpl = _read("decision_reward.md")
    return tmpl.format(
        round=obs.round,
        state_block=_state_block(obs, cfg),
        distribution_block=_distribution_block(obs, cfg),
        max_spend=cfg.reward_max_spend,
        own_balance=obs.own_balance,
        reward_ratio=cfg.reward_ratio,
    )


def build_punish_prompt(obs: Observation, cfg: GameConfig) -> str:
    tmpl = _read("decision_punish.md")
    block = _distribution_block(obs, cfg)
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
