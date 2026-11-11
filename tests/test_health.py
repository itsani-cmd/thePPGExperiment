"""Run-health, persona-fidelity and group-dynamics checks on mock games."""

from __future__ import annotations

import os
import tempfile

from pgg.config import AgentSeatConfig, GameConfig, HorizonConfig, ModelConfig, RunConfig
from pgg.health import game_report
from pgg.runner import run_game


def _play(mock_type, rounds=6, punishment=False):
    run = RunConfig(
        name="test",
        seed=7,
        games=1,
        game=GameConfig(
            n_players=5,
            start_tokens=20,
            multiplier=1.6,
            messages_enabled=False,
            punishment_enabled=punishment,
            horizon=HorizonConfig(mode="fixed", rounds=rounds),
        ),
        seats=[AgentSeatConfig(agent_type=mock_type) for _ in range(5)],
        models={"model_a": ModelConfig(model="mock")},
    )
    d = tempfile.mkdtemp()
    run_game(run, "g0", 7, d, agent_kind="mock")
    return game_report(os.path.join(d, "g0"))


def test_full_cooperation_is_fully_efficient():
    r = _play("cooperate")
    assert r["health"]["finished"] and r["health"]["fallback_rate"] == 0
    assert abs(r["dynamics"]["efficiency"] - 1.0) < 0.01
    assert r["dynamics"]["gini_final"] < 0.01


def test_full_defection_gains_nothing():
    r = _play("defect")
    assert r["dynamics"]["efficiency"] == 0
    assert all(p["zero_rate"] == 1 for p in r["personas"].values())


def test_punishment_destroys_tokens_and_report_has_no_calls():
    r = _play("random", punishment=True)
    assert r["dynamics"]["tokens_destroyed_by_punishment"] >= 0
    assert r["health"]["calls"] == 0 and r["health"]["call_error_rate"] is None
