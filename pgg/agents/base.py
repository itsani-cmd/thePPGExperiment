"""Agent interface and the structured I/O types shared by all agents.

The engine never imports this module; agents translate an :class:`Observation`
(built by the runner from the public game log) into the per-phase outputs the
engine consumes. Keeping agents stateless — rebuilding the observation from the
log each call — makes resume and audit straightforward.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Protocol, runtime_checkable

from pydantic import BaseModel, Field


class MessageView(BaseModel):
    seat: str
    text: str


class RoundPublic(BaseModel):
    """Everything public about a completed round, as seen by any agent."""

    round: int
    speaker_order: List[str] = Field(default_factory=list)
    messages: List[MessageView] = Field(default_factory=list)
    contributions: Dict[str, int] = Field(default_factory=dict)
    exited: List[str] = Field(default_factory=list)
    share: int = 0
    pot: int = 0
    balances_after_distribution: Dict[str, int] = Field(default_factory=dict)
    # punishment: list of (punisher, target, spend, actual_damage)
    punishments: List[Dict[str, object]] = Field(default_factory=list)
    balances_after_punishment: Dict[str, int] = Field(default_factory=dict)


class Observation(BaseModel):
    """What an agent sees at decision time for one phase."""

    seat: str
    seat_labels: List[str]
    round: int
    phase: str  # 'message' | 'contribute' | 'punish' | 'intent_probe'
    balances: Dict[str, int]
    own_balance: int
    history: List[RoundPublic] = Field(default_factory=list)
    # messages already spoken THIS round (sequential visibility)
    messages_this_round: List[MessageView] = Field(default_factory=list)
    # distribution result available in the punish phase
    this_round_contributions: Optional[Dict[str, int]] = None
    this_round_share: Optional[int] = None
    this_round_exited: List[str] = Field(default_factory=list)
    # horizon disclosure (condition-dependent)
    horizon_text: str = ""
    is_final_round: bool = False


class MessageOut(BaseModel):
    message: str = ""
    norm_stated: bool = False


class ContributionOut(BaseModel):
    contribution: int
    reason: str = ""
    predicted_others_mean: Optional[float] = None
    exit: bool = False  # sit the round out (only honoured when the exit option is on)


class PunishOut(BaseModel):
    target: Optional[str] = None
    spend: int = 0
    reason: str = ""
    expected_effect: str = ""


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
