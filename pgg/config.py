"""Pydantic configuration schemas for the PGG harness.

A YAML config resolves into a :class:`RunConfig`. The engine only ever receives
a :class:`GameConfig` (the pure game parameters); model/seat wiring lives in the
runner layer so the engine stays free of I/O and LLM concerns.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from pydantic import BaseModel, Field, model_validator


class HorizonConfig(BaseModel):
    """Game-length rule.

    ``fixed``: play exactly ``rounds`` rounds.
    ``geometric``: pre-sample length from a geometric distribution with
    ``p_continue`` (capped at ``max_rounds``); length is hidden from agents.
    """

    mode: str = "fixed"
    rounds: int = 10
    p_continue: float = 0.9
    max_rounds: int = 30

    @model_validator(mode="after")
    def _check(self) -> "HorizonConfig":
        if self.mode not in ("fixed", "geometric"):
            raise ValueError("horizon.mode must be 'fixed' or 'geometric'")
        if self.mode == "fixed" and self.rounds < 1:
            raise ValueError("horizon.rounds must be >= 1")
        if self.mode == "geometric":
            if not (0.0 < self.p_continue < 1.0):
                raise ValueError("horizon.p_continue must be in (0, 1)")
            if self.max_rounds < 1:
                raise ValueError("horizon.max_rounds must be >= 1")
        return self


class GameConfig(BaseModel):
    """Pure game parameters consumed by the engine.

    All token quantities are integers. ``multiplier`` is stored as a float for
    config ergonomics but the engine converts it to an exact ``Fraction`` and
    never does floating-point arithmetic on tokens.
    """

    n_players: int = 5
    rounds: int = 10  # convenience mirror of horizon for fixed mode
    start_tokens: int = 20
    multiplier: float = 1.6

    messages_enabled: bool = True
    message_mode: str = "sequential"  # 'sequential' | 'simultaneous'
    message_max_chars: int = 300

    punishment_enabled: bool = True
    punish_max_spend: int = 10
    punish_ratio: int = 3
    punish_cap_fraction: float = 0.5
    punish_cap_abs: int = 100
    punishment_in_final_round: bool = True
    announce_final_round_rules: bool = True

    horizon: HorizonConfig = Field(default_factory=HorizonConfig)

    goal_wording: str = "relative"  # 'relative' | 'absolute'
    show_all_balances: bool = True
    intent_probe: bool = False

    # metrics thresholds (kept here so logs + metrics agree)
    free_rider_fraction_threshold: float = 0.25

    @model_validator(mode="after")
    def _check(self) -> "GameConfig":
        if self.n_players < 2:
            raise ValueError("n_players must be >= 2")
        if self.start_tokens < 0:
            raise ValueError("start_tokens must be >= 0")
        if self.multiplier <= 0:
            raise ValueError("multiplier must be > 0")
        if self.message_mode not in ("sequential", "simultaneous"):
            raise ValueError("message_mode must be 'sequential' or 'simultaneous'")
        if self.goal_wording not in ("relative", "absolute"):
            raise ValueError("goal_wording must be 'relative' or 'absolute'")
        if self.punish_ratio < 1:
            raise ValueError("punish_ratio must be >= 1")
        # keep the convenience mirror in sync with a fixed horizon
        if self.horizon.mode == "fixed":
            self.rounds = self.horizon.rounds
        return self


class ModelConfig(BaseModel):
    """Per-model endpoint and sampling settings."""

    model: str
    base_url: Optional[str] = None
    temperature: float = 1.0
    max_tokens: int = 1024
    reasoning: Optional[str] = None  # reasoning effort if the endpoint supports it
    json_mode: bool = True  # request response_format json when supported


class AgentSeatConfig(BaseModel):
    """One seat's wiring: which persona/principal/model it uses.

    ``persona`` and ``principal`` are persona ids resolved against
    ``personas/PERSONAS.md``. ``null`` means the baseline (no persona text).
    ``agent_type`` selects a mock agent when not using an LLM.
    """

    persona: Optional[str] = None
    principal: Optional[str] = None
    model: Optional[str] = None
    agent_type: Optional[str] = None  # mock agents: cooperate|defect|titfortat|random


class RunConfig(BaseModel):
    """Top-level resolved config for a batch of games."""

    name: str = "unnamed"
    game: GameConfig = Field(default_factory=GameConfig)
    seats: List[AgentSeatConfig] = Field(default_factory=list)
    models: Dict[str, ModelConfig] = Field(default_factory=dict)
    seed: int = 1234
    games: int = 1
    personas_file: str = "personas/PERSONAS.md"

    @model_validator(mode="after")
    def _check(self) -> "RunConfig":
        if self.seats and len(self.seats) != self.game.n_players:
            raise ValueError(
                f"number of seats ({len(self.seats)}) must equal "
                f"game.n_players ({self.game.n_players})"
            )
        return self


def load_run_config(path: str) -> RunConfig:
    """Load a YAML file into a RunConfig.

    Accepts the flat structure used by the preset files:
    ``game:``, ``seats:``, ``models:``, ``seed:``, ``games:``, ``name:``.
    """
    import yaml

    with open(path, "r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    return RunConfig(**data)
