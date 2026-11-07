"""Shared setup for the mechanism tests (exit, rewards, anonymity, scripted seats).

Two levels of helper: ``make_game`` / ``contribute`` drive the engine directly for
rule-level tests, and ``run_config`` / ``play`` run whole mock games and return the
parsed ``rounds.jsonl`` for end-to-end tests.
"""

from __future__ import annotations

import json
import os
import tempfile
from typing import Dict, List, Sequence, Tuple

from pgg.config import AgentSeatConfig, GameConfig, HorizonConfig, ModelConfig, RunConfig
from pgg.engine import Game
from pgg.runner import run_game

SEATS = ["P1", "P2", "P3", "P4", "P5"]
SEED = 11


def make_game(rounds: int = 3, **game_kw) -> Game:
    """A 5-seat game with the first round already begun."""
    cfg = GameConfig(horizon=HorizonConfig(mode="fixed", rounds=rounds), **game_kw)
    g = Game(cfg, SEATS, seed=1)
    g.begin_round()
    return g


def contribute(g: Game, amounts: Sequence[int], exits: Sequence[str] = ()) -> None:
    """Submit one contribution per seat (P1..P5) and resolve the distribution."""
    for seat, amount in zip(SEATS, amounts):
        g.submit_contribution(seat, amount, exit=seat in exits)
    g.resolve_contributions_and_distribution()


def run_config(
    seats: List[AgentSeatConfig], rounds: int = 4, **game_kw
) -> RunConfig:
    """A run config with messages off, so a round is contribute (+ reward) (+ punish)."""
    return RunConfig(
        name="t",
        seed=SEED,
        games=1,
        game=GameConfig(
            messages_enabled=False,
            horizon=HorizonConfig(mode="fixed", rounds=rounds),
            **game_kw,
        ),
        seats=seats,
        models={"m": ModelConfig(model="mock")},
    )


def play(
    agent_types: Sequence[str], rounds: int = 6, **game_kw
) -> Tuple[Dict, List[dict]]:
    """Play one mock game; return (summary, parsed rounds.jsonl)."""
    run = run_config([AgentSeatConfig(agent_type=t) for t in agent_types], rounds, **game_kw)
    out_dir = tempfile.mkdtemp()
    summary = run_game(run, "g0", SEED, out_dir, agent_kind="mock")
    with open(os.path.join(out_dir, "g0", "rounds.jsonl")) as f:
        return summary, [json.loads(line) for line in f if line.strip()]
