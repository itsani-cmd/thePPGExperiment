"""Agent interface and the structured I/O types shared by all agents.

The engine never imports this module; agents translate an :class:`Observation`
(built by the runner from the public game log) into the per-phase outputs the
engine consumes. Keeping agents stateless — rebuilding the observation from the
log each call — makes resume and audit straightforward.
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Protocol, runtime_checkable

from pydantic import BaseModel, Field, field_validator


class MessageView(BaseModel):
    seat: str
    text: str


class RoundPublic(BaseModel):
    """Everything public about a completed round, as seen by any agent."""

    round: int
    speaker_order: List[str] = Field(default_factory=list)
    messages: List[MessageView] = Field(default_factory=list)
    contributions: Dict[str, int] = Field(default_factory=dict)
    # group total; in anonymous mode ``contributions`` holds only the viewer's own entry
    total_contributed: int = 0
    exited: List[str] = Field(default_factory=list)
    share: int = 0
    pot: int = 0
    balances_after_distribution: Dict[str, int] = Field(default_factory=dict)
    # rewards: list of dicts with giver, target, spend, gain
    rewards: List[Dict[str, object]] = Field(default_factory=list)
    # punishment: list of (punisher, target, spend, actual_damage)
    punishments: List[Dict[str, object]] = Field(default_factory=list)
    balances_after_punishment: Dict[str, int] = Field(default_factory=dict)


class Observation(BaseModel):
    """What an agent sees at decision time for one phase."""

    seat: str
    seat_labels: List[str]
    round: int
    phase: str  # 'message' | 'contribute' | 'reward' | 'punish' | 'intent_probe'
    balances: Dict[str, int]
    own_balance: int
    history: List[RoundPublic] = Field(default_factory=list)
    # messages already spoken THIS round (sequential visibility)
    messages_this_round: List[MessageView] = Field(default_factory=list)
    # distribution result available in the punish phase
    this_round_contributions: Optional[Dict[str, int]] = None
    this_round_share: Optional[int] = None
    this_round_total: Optional[int] = None
    this_round_exited: List[str] = Field(default_factory=list)
    # horizon disclosure (condition-dependent)
    horizon_text: str = ""
    is_final_round: bool = False


def _strip_tags(v: str) -> str:
    """Drop stray XML-like tags (e.g. a copied ``</intent>``) from a survey answer."""
    return re.sub(r"</?[A-Za-z_][A-Za-z0-9_ ]*>", "", v).strip()


def _lenient_int(v):
    """Coerce a survey number to int, or None if it can't be read.

    Survey fields are optional extras: a bad value must never fail the whole
    reply (that would drop the message and trigger a fallback).
    """
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, int):
        return v
    if isinstance(v, float):
        return int(v) if v.is_integer() else round(v)
    if isinstance(v, str):
        m = re.search(r"-?\d+", _strip_tags(v))
        return int(m.group()) if m else None
    return None


class MessageOut(BaseModel):
    message: str = ""
    norm_stated: bool = False
    # Private communication plan (survey). Never shown to other players; logged
    # per round under ``message_plans`` for the promise-keeping metrics.
    intent: Optional[str] = None
    claimed_contribution: Optional[int] = None
    intended_contribution: Optional[int] = None

    @field_validator("intent", mode="before")
    @classmethod
    def _clean_intent(cls, v):
        if not isinstance(v, str):
            return None
        return _strip_tags(v) or None

    @field_validator("claimed_contribution", "intended_contribution", mode="before")
    @classmethod
    def _clean_amount(cls, v):
        return _lenient_int(v)

    def plan(self) -> Dict[str, object]:
        """The private plan as stored in the round log."""
        return {
            "intent": self.intent,
            "claimed_contribution": self.claimed_contribution,
            "intended_contribution": self.intended_contribution,
            "sent_message": bool(self.message),
        }


class ContributionOut(BaseModel):
    contribution: int = 0  # ignored (and may be null/omitted) when exit is true
    reason: str = ""
    predicted_others_mean: Optional[float] = None
    exit: bool = False  # sit the round out (only honoured when the exit option is on)

    @field_validator("contribution", mode="before")
    @classmethod
    def _null_contribution_is_zero(cls, v):
        return 0 if v is None else v


class RewardOut(BaseModel):
    target: Optional[str] = None
    spend: int = 0
    reason: str = ""


class PunishOut(BaseModel):
    target: Optional[str] = None
    spend: int = 0
    reason: str = ""
    expected_effect: str = ""

    @field_validator("reason", "expected_effect", mode="before")
    @classmethod
    def _null_text_is_empty(cls, v):
        # A "do nothing" reply often sends "expected_effect": null; that is a valid
        # decision, not a schema error worth a retry or a fallback.
        return "" if v is None else v


class IntentProbeEntry(BaseModel):
    seat: str
    expected_next_contribution: float
    deception_rank: int


class IntentProbeOut(BaseModel):
    probes: List[IntentProbeEntry] = Field(default_factory=list)


@runtime_checkable
class Agent(Protocol):
    """The interface every agent implements. Each method is one decision."""

    def message(self, obs: Observation) -> Optional[MessageOut]:
        ...

    def contribute(self, obs: Observation) -> ContributionOut:
        ...

    def punish(self, obs: Observation) -> PunishOut:
        ...
