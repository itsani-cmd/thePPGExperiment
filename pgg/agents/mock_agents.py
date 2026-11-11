"""Deterministic mock agents. No LLM, no network — used for offline runs and tests.

All randomness is seeded from (game seed, seat, round, phase) so a game with
mock agents reproduces byte-for-byte across runs.
"""

from __future__ import annotations

import random
from typing import Optional

from ..engine import stable_seed
from .base import (
    Agent,
    ContributionOut,
    MessageOut,
    Observation,
    PunishOut,
    RewardOut,
)


class _MockBase:
    """Shared helpers. Subclasses implement contribute/punish behavior."""

    name = "mock"

    def __init__(self, seed: int = 0):
        self.seed = seed

    def _rng(self, obs: Observation) -> random.Random:
        return random.Random(stable_seed(self.seed, obs.seat, obs.round, obs.phase))

    def message(self, obs: Observation) -> Optional[MessageOut]:
        return None  # mocks stay silent by default

    def punish(self, obs: Observation) -> PunishOut:
        return PunishOut(target=None, spend=0, reason="mock: no punishment")

    def reward(self, obs: Observation) -> RewardOut:
        return RewardOut(target=None, spend=0, reason="mock: no reward")

    def _last_round(self, obs: Observation):
        return obs.history[-1] if obs.history else None


class AlwaysCooperate(_MockBase):
    name = "cooperate"

    def contribute(self, obs: Observation) -> ContributionOut:
        return ContributionOut(
            contribution=obs.own_balance,
            reason="mock: always cooperate (contribute everything)",
            predicted_others_mean=float(obs.own_balance),
        )


class AlwaysDefect(_MockBase):
    name = "defect"

    def contribute(self, obs: Observation) -> ContributionOut:
        return ContributionOut(
            contribution=0,
            reason="mock: always defect (contribute nothing)",
            predicted_others_mean=0.0,
        )


class TitForTat(_MockBase):
    """Contribute the mean of others' previous-round contributions.

    Round 1 cooperates fully (contributes its whole balance, like the classic
    'nice' opening). Thereafter it mirrors the others' average last round,
    clamped to its balance.
    """

    name = "titfortat"

    def contribute(self, obs: Observation) -> ContributionOut:
        last = self._last_round(obs)
        if last is None:
            amt = obs.own_balance
            pred = float(obs.own_balance)
        else:
            others = [
                c for s, c in last.contributions.items() if s != obs.seat
            ]
            if not others and last.total_contributed:
                # anonymous mode: only the group total is visible
                # exiters contributed nothing; only our own exit is visible under anonymity
                n_others = max(1, len(obs.seat_labels) - 1 - len([e for e in last.exited if e != obs.seat]))
                own = last.contributions.get(obs.seat, 0)
                others = [(last.total_contributed - own) / n_others]
            mean = sum(others) / len(others) if others else 0
            amt = int(round(mean))
            amt = max(0, min(amt, obs.own_balance))
            pred = float(mean)
        return ContributionOut(
            contribution=amt,
            reason="mock: tit-for-tat (mirror others' last mean)",
            predicted_others_mean=pred,
        )

    def punish(self, obs: Observation) -> PunishOut:
        """Punish whoever punished me last round (spend 3), else nothing."""
        last = self._last_round(obs)
        if last is None:
            return PunishOut(target=None, spend=0, reason="mock: no history")
        for p in last.punishments:
            if p.get("target") == obs.seat and int(p.get("actual_damage", 0)) > 0:
                attacker = p.get("punisher")
                if attacker and attacker != obs.seat:
                    return PunishOut(
                        target=str(attacker),
                        spend=3,
                        reason="mock: retaliate against last-round punisher",
                        expected_effect="deter future punishment",
                    )
        return PunishOut(target=None, spend=0, reason="mock: nobody punished me")


class RandomAgent(_MockBase):
    name = "random"

    def contribute(self, obs: Observation) -> ContributionOut:
        rng = self._rng(obs)
        amt = rng.randint(0, obs.own_balance)
        return ContributionOut(
            contribution=amt,
            reason="mock: random contribution",
            predicted_others_mean=None,
        )

    def punish(self, obs: Observation) -> PunishOut:
        rng = self._rng(obs)
        if rng.random() < 0.25:
            others = [s for s in obs.seat_labels if s != obs.seat]
            if others:
                target = rng.choice(others)
                spend = rng.randint(1, 10)
                return PunishOut(
                    target=target,
                    spend=spend,
                    reason="mock: random punishment",
                    expected_effect="random",
                )
        return PunishOut(target=None, spend=0, reason="mock: random no-op")

    def reward(self, obs: Observation) -> RewardOut:
        rng = self._rng(obs)
        if rng.random() < 0.25:
            others = [s for s in obs.seat_labels if s != obs.seat]
            if others:
                return RewardOut(
                    target=rng.choice(others),
                    spend=rng.randint(1, 10),
                    reason="mock: random reward",
                )
        return RewardOut(target=None, spend=0, reason="mock: random no-op")


class Leaver(_MockBase):
    """Always sits the round out when the exit option exists (else contributes 0)."""

    name = "leaver"

    def contribute(self, obs: Observation) -> ContributionOut:
        return ContributionOut(
            contribution=0, reason="mock: always exit", predicted_others_mean=None, exit=True
        )


MOCK_AGENTS = {
    "cooperate": AlwaysCooperate,
    "defect": AlwaysDefect,
    "titfortat": TitForTat,
    "random": RandomAgent,
    "leaver": Leaver,
}


def make_mock(agent_type: str, seed: int = 0) -> Agent:
    if agent_type not in MOCK_AGENTS:
        raise ValueError(
            f"unknown mock agent '{agent_type}'; choices: {sorted(MOCK_AGENTS)}"
        )
    return MOCK_AGENTS[agent_type](seed=seed)
