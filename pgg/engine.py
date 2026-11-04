"""Pure, deterministic PGG game engine.

No I/O, no LLM calls, no randomness beyond what a caller injects. All token
quantities are integers; the multiplier is applied with exact rational
arithmetic (``fractions.Fraction``), never floating point.

The engine exposes a phase-stepped :class:`Game` so the runner can interleave
agent calls between phases, plus dataclasses that double as the structured round
log. Everything here is deterministic given its inputs, which makes it directly
unit-testable without any agents.
"""

from __future__ import annotations

import hashlib
import math
import random
from dataclasses import dataclass, field
from fractions import Fraction
from typing import Dict, List, Optional, Sequence

from .config import GameConfig


def stable_seed(*parts) -> int:
    """Deterministic, process-independent integer seed from arbitrary parts.

    Python's ``hash()`` is salted per process (PYTHONHASHSEED), so seeding an
    RNG with a tuple is neither stable across runs nor supported. We hash the
    stringified parts with blake2b instead so logs reproduce byte-for-byte in
    any process.
    """
    key = "|".join(str(p) for p in parts).encode("utf-8")
    digest = hashlib.blake2b(key, digest_size=8).digest()
    return int.from_bytes(digest, "big")


# --------------------------------------------------------------------------- #
# Data structures (also serve as the structured round record)
# --------------------------------------------------------------------------- #
@dataclass
class MessageAction:
    seat: str
    text: str
    truncated: bool = False
    norm_stated: bool = False
    fallback_used: bool = False


@dataclass
class PunishAction:
    """A single punishment action, with resolved economics filled in by the engine."""

    punisher: str
    target: Optional[str]
    spend: int
    # resolved by the engine:
    cost: int = 0
    damage: int = 0  # nominal damage before over-kill clamp
    actual_damage: int = 0  # damage after clamping the target at 0
    refund: int = 0
    reason: str = ""
    expected_effect: str = ""
    fallback_used: bool = False


@dataclass
class RoundRecord:
    round: int
    speaker_order: List[str] = field(default_factory=list)
    messages: List[MessageAction] = field(default_factory=list)

    balances_before_contribution: Dict[str, int] = field(default_factory=dict)
    contributions: Dict[str, int] = field(default_factory=dict)
    contribution_fallbacks: Dict[str, bool] = field(default_factory=dict)
    balances_after_contribution: Dict[str, int] = field(default_factory=dict)

    carry_in: int = 0
    pot: int = 0
    share: int = 0
    carry_out: int = 0
    balances_after_distribution: Dict[str, int] = field(default_factory=dict)

    punishment_applied: bool = True
    punishments: List[PunishAction] = field(default_factory=list)
    balances_after_punishment: Dict[str, int] = field(default_factory=dict)


# --------------------------------------------------------------------------- #
# Pure resolution helpers (the math the tests pin down)
# --------------------------------------------------------------------------- #
def multiplier_fraction(multiplier: float) -> Fraction:
    """Convert a config multiplier to an exact Fraction (e.g. 1.6 -> 8/5)."""
    return Fraction(multiplier).limit_denominator(1_000_000)


def resolve_distribution(
    contributions: Sequence[int],
    carry_in: int,
    multiplier: float,
    n_players: int,
) -> Dict[str, int]:
    """Compute pot/share/carry from contributions using exact arithmetic.

    ``pot = floor(sum(c) * multiplier + carry_in)`` with the multiplication done
    as an exact Fraction. ``share = pot // n``; ``carry = pot - n*share``.
    """
    frac = multiplier_fraction(multiplier)
    total = sum(contributions)
    pot_exact = frac * total + carry_in
    pot = int(math.floor(pot_exact))
    share = pot // n_players
    carry_out = pot - n_players * share
    return {"pot": pot, "share": share, "carry_out": carry_out}


def _nominal_damage(spend: int, target_balance: int, cfg: GameConfig) -> int:
    """damage = min(ratio*spend, floor(cap_fraction*B), cap_abs), integer."""
    cap_frac = int(math.floor(Fraction(cfg.punish_cap_fraction).limit_denominator(1_000_000) * target_balance))
    return min(cfg.punish_ratio * spend, cap_frac, cfg.punish_cap_abs)


def _cost_for_damage(damage: int, cfg: GameConfig) -> int:
    """cost = ceil(damage / ratio)."""
    if damage <= 0:
        return 0
    return -(-damage // cfg.punish_ratio)  # ceil division for non-negative ints


# --------------------------------------------------------------------------- #
# The game
# --------------------------------------------------------------------------- #
class Game:
    """A phase-stepped game instance.

    Typical driver loop (see runner)::

        g = Game(cfg, seats, seed)
        while not g.finished:
            g.begin_round()
            # messages phase
            order = g.message_order()
            for seat in order:
                g.submit_message(seat, text, ...)
            g.close_messages()
            # contributions
            for seat in seats: g.submit_contribution(seat, c)
            g.resolve_contributions_and_distribution()
            # punishment
            if g.punishment_active():
                for seat in seats: g.submit_punishment(seat, target, spend, ...)
            g.resolve_punishment()
            g.end_round()
    """

    def __init__(self, cfg: GameConfig, seats: Sequence[str], seed: int):
        self.cfg = cfg
        self.seats: List[str] = list(seats)
        self.seed = seed
        self._rng = random.Random(seed)

        self.balances: Dict[str, int] = {s: cfg.start_tokens for s in self.seats}
        self.carry: int = 0
        self.round: int = 1
        self.history: List[RoundRecord] = []

        self.total_rounds = self._sample_horizon()

        # per-round scratch
        self._rec: Optional[RoundRecord] = None
        self._pending_contrib: Dict[str, int] = {}
        self._pending_punish: List[PunishAction] = []
        self._phase_messages: List[MessageAction] = []

    # ---- horizon -------------------------------------------------------- #
    def _sample_horizon(self) -> int:
        h = self.cfg.horizon
        if h.mode == "fixed":
            return h.rounds
        # geometric: round 1 always played; each subsequent round continues with
        # probability p_continue. Uses a dedicated RNG stream derived from seed so
        # it is reproducible and independent of later message-order draws.
        rng = random.Random(stable_seed(self.seed, "horizon"))
        length = 1
        while length < h.max_rounds:
            if rng.random() < h.p_continue:
                length += 1
            else:
                break
        return length

    @property
    def finished(self) -> bool:
        return self.round > self.total_rounds

    def is_final_round(self) -> bool:
        return self.round == self.total_rounds

    # ---- round lifecycle ------------------------------------------------ #
    def begin_round(self) -> RoundRecord:
        assert not self.finished, "game already finished"
        rec = RoundRecord(round=self.round, carry_in=self.carry)
        rec.balances_before_contribution = dict(self.balances)
        self._rec = rec
        self._pending_contrib = {}
        self._pending_punish = []
        self._phase_messages = []
        return rec

    # ---- messages ------------------------------------------------------- #
    def messages_active(self) -> bool:
        return self.cfg.messages_enabled

    def message_order(self) -> List[str]:
        """Random speaker order for this round (logged). Deterministic per seed+round."""
        order = list(self.seats)
        rng = random.Random(stable_seed(self.seed, "msgorder", self.round))
        rng.shuffle(order)
        self._rec.speaker_order = list(order)
        return order

    def submit_message(
        self,
        seat: str,
        text: str,
        norm_stated: bool = False,
        fallback_used: bool = False,
    ) -> MessageAction:
        truncated = False
        if text is None:
            text = ""
        if len(text) > self.cfg.message_max_chars:
            text = text[: self.cfg.message_max_chars]
            truncated = True
        action = MessageAction(
            seat=seat,
            text=text,
            truncated=truncated,
            norm_stated=bool(norm_stated),
            fallback_used=fallback_used,
        )
        self._phase_messages.append(action)
        return action

    def messages_so_far(self) -> List[MessageAction]:
        """Messages submitted this round so far (for sequential visibility)."""
        return list(self._phase_messages)

    def close_messages(self) -> None:
        self._rec.messages = list(self._phase_messages)

    # ---- contributions -------------------------------------------------- #
    def submit_contribution(self, seat: str, amount: int, fallback_used: bool = False) -> int:
        """Clamp and record a contribution. Clamped to [0, balance]."""
        bal = self.balances[seat]
        c = int(amount)
        if c < 0:
            c = 0
        if c > bal:
            c = bal
        self._pending_contrib[seat] = c
        self._rec.contribution_fallbacks[seat] = bool(fallback_used)
        return c

    def resolve_contributions_and_distribution(self) -> None:
        rec = self._rec
        # default any missing seat to 0 (defensive)
        for s in self.seats:
            self._pending_contrib.setdefault(s, 0)
            rec.contribution_fallbacks.setdefault(s, False)
        rec.contributions = dict(self._pending_contrib)

        # drop balances by contributions
        for s in self.seats:
            self.balances[s] -= self._pending_contrib[s]
        rec.balances_after_contribution = dict(self.balances)

        dist = resolve_distribution(
            [self._pending_contrib[s] for s in self.seats],
            self.carry,
            self.cfg.multiplier,
            self.cfg.n_players,
        )
        rec.pot = dist["pot"]
        rec.share = dist["share"]
        rec.carry_out = dist["carry_out"]
        for s in self.seats:
            self.balances[s] += dist["share"]
        self.carry = dist["carry_out"]
        rec.balances_after_distribution = dict(self.balances)

    # ---- punishment ----------------------------------------------------- #
    def punishment_active(self) -> bool:
        if not self.cfg.punishment_enabled:
            return False
        if self.is_final_round() and not self.cfg.punishment_in_final_round:
            return False
        return True

    def submit_punishment(
        self,
        punisher: str,
        target: Optional[str],
        spend: int,
        reason: str = "",
        expected_effect: str = "",
        fallback_used: bool = False,
    ) -> PunishAction:
        """Validate and record a punishment intent. Invalid actions become no-ops.

        Rules enforced here: cannot target self, target must be a real seat,
        spend in [0, min(max_spend, balance)]. Economics are resolved later from
        the post-distribution snapshot in :meth:`resolve_punishment`.
        """
        spend = int(spend)
        valid_target = (
            target is not None and target in self.seats and target != punisher
        )
        if not valid_target:
            target = None
            spend = 0
        max_spend = min(self.cfg.punish_max_spend, self.balances[punisher])
        if spend < 0:
            spend = 0
        if spend > max_spend:
            spend = max_spend
        if spend == 0:
            target = None
        action = PunishAction(
            punisher=punisher,
            target=target,
            spend=spend,
            reason=reason,
            expected_effect=expected_effect,
            fallback_used=fallback_used,
        )
        self._pending_punish.append(action)
        return action

    def resolve_punishment(self) -> None:
        """Resolve all punishments simultaneously against the post-distribution snapshot."""
        rec = self._rec
        rec.punishment_applied = True
        snapshot = dict(self.balances)  # B: post-distribution balances

        # First pass: nominal damage + cost + refund from the snapshot.
        for a in self._pending_punish:
            if a.target is None or a.spend <= 0:
                a.cost = 0
                a.damage = 0
                a.actual_damage = 0
                a.refund = a.spend  # spend was forced to 0 for no-ops
                continue
            a.damage = _nominal_damage(a.spend, snapshot[a.target], self.cfg)
            a.cost = _cost_for_damage(a.damage, self.cfg)
            a.refund = a.spend - a.cost

        # Deduct punisher costs.
        for a in self._pending_punish:
            if a.cost:
                self.balances[a.punisher] -= a.cost

        # Second pass: apply damage per target, clamping total at the target's
        # snapshot balance and splitting actual_damage proportionally to nominal.
        by_target: Dict[str, List[PunishAction]] = {}
        for a in self._pending_punish:
            if a.target is not None and a.damage > 0:
                by_target.setdefault(a.target, []).append(a)

        for target, actions in by_target.items():
            total_nominal = sum(a.damage for a in actions)
            cap = snapshot[target]
            if total_nominal <= cap:
                for a in actions:
                    a.actual_damage = a.damage
                self.balances[target] -= total_nominal
            else:
                # Proportional allocation of the available `cap` damage, largest-
                # remainder rounding so the shares are integers summing to cap.
                allocations = _proportional_allocation(
                    [a.damage for a in actions], cap
                )
                for a, alloc in zip(actions, allocations):
                    a.actual_damage = alloc
                self.balances[target] = 0
            if self.balances[target] < 0:
                self.balances[target] = 0

        rec.punishments = list(self._pending_punish)
        rec.balances_after_punishment = dict(self.balances)

    def skip_punishment(self) -> None:
        """Record that punishment did not occur this round."""
        rec = self._rec
        rec.punishment_applied = False
        rec.punishments = []
        rec.balances_after_punishment = dict(self.balances)

    # ---- end of round --------------------------------------------------- #
    def end_round(self) -> RoundRecord:
        rec = self._rec
        # ensure the final balance snapshot is set even if punishment was skipped
        if not rec.balances_after_punishment:
            rec.balances_after_punishment = dict(self.balances)
        self.history.append(rec)
        self._rec = None
        self.round += 1
        return rec

    # ---- scoring -------------------------------------------------------- #
    def scores(self) -> Dict[str, Dict[str, float]]:
        """Final balances, ranks (average rank for ties), totals."""
        final = dict(self.balances)
        ranks = average_ranks(final)
        return {
            seat: {"final_tokens": final[seat], "rank": ranks[seat]}
            for seat in self.seats
        }


# --------------------------------------------------------------------------- #
# Small pure utilities
# --------------------------------------------------------------------------- #
def _proportional_allocation(weights: List[int], total: int) -> List[int]:
    """Allocate ``total`` across ``weights`` proportionally, integer, summing to total.

    Uses largest-remainder (Hamilton) rounding for determinism.
    """
    wsum = sum(weights)
    if wsum == 0 or total <= 0:
        return [0 for _ in weights]
    raw = [Fraction(total * w, wsum) for w in weights]
    floors = [int(r) for r in raw]
    remainder = total - sum(floors)
    # distribute leftover to the largest fractional parts, tie-break by index
    order = sorted(
        range(len(weights)),
        key=lambda i: (raw[i] - floors[i], weights[i], -i),
        reverse=True,
    )
    for i in order[:remainder]:
        floors[i] += 1
    return floors


def average_ranks(balances: Dict[str, int]) -> Dict[str, float]:
    """Rank 1 = most tokens. Ties share the average of their rank positions."""
    seats = list(balances.keys())
    # sort descending by balance
    ordered = sorted(seats, key=lambda s: balances[s], reverse=True)
    ranks: Dict[str, float] = {}
    i = 0
    n = len(ordered)
    while i < n:
        j = i
        while j + 1 < n and balances[ordered[j + 1]] == balances[ordered[i]]:
            j += 1
        # positions i+1 .. j+1 (1-indexed) share the average
        avg = sum(range(i + 1, j + 2)) / (j - i + 1)
        for k in range(i, j + 1):
            ranks[ordered[k]] = avg
        i = j + 1
    return ranks
