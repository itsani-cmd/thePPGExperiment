"""Mock-agent behavior and byte-for-byte determinism of logs."""

from __future__ import annotations

import json
import os
import tempfile

from pgg.config import AgentSeatConfig, GameConfig, HorizonConfig, ModelConfig, RunConfig
from pgg.runner import run_game


def _run_config(mock_type, messages=False, rounds=10, punishment=True):
    return RunConfig(
        name="test",
        seed=1234,
        games=1,
        game=GameConfig(
            n_players=5,
            start_tokens=20,
            multiplier=1.6,
            messages_enabled=messages,
            punishment_enabled=punishment,
            horizon=HorizonConfig(mode="fixed", rounds=rounds),
        ),
        seats=[AgentSeatConfig(agent_type=mock_type) for _ in range(5)],
        models={"model_a": ModelConfig(model="mock")},
    )


def test_all_defect_balances():
    # all contribute 0 every round -> balances stay at start (minus any punishment)
    run = _run_config("defect", punishment=False)
    with tempfile.TemporaryDirectory() as d:
        summary = run_game(run, "g0", 1234, d, agent_kind="mock")
        for s, v in summary["final_balances"].items():
            assert v == 20


def test_all_cooperate_grows():
    run = _run_config("cooperate", punishment=False)
    with tempfile.TemporaryDirectory() as d:
        summary = run_game(run, "g0", 1234, d, agent_kind="mock")
        # everyone contributes everything each round; balances must grow > start
        for v in summary["final_balances"].values():
            assert v > 20


def test_cooperate_vs_defect_first_round():
    # 4 cooperate (contribute 20), 1 defect: defector ends round 1 at 45.
    run = RunConfig(
        name="mix",
        seed=1234,
        games=1,
        game=GameConfig(
            n_players=5,
            start_tokens=20,
            multiplier=1.6,
            messages_enabled=False,
            punishment_enabled=False,
            horizon=HorizonConfig(mode="fixed", rounds=1),
        ),
        seats=[
            AgentSeatConfig(agent_type="defect"),
            AgentSeatConfig(agent_type="cooperate"),
            AgentSeatConfig(agent_type="cooperate"),
            AgentSeatConfig(agent_type="cooperate"),
            AgentSeatConfig(agent_type="cooperate"),
        ],
        models={"model_a": ModelConfig(model="mock")},
    )
    with tempfile.TemporaryDirectory() as d:
        summary = run_game(run, "g0", 1234, d, agent_kind="mock")
        balances = sorted(summary["final_balances"].values())
        # one defector at 45, four cooperators at 25
        assert balances == [25, 25, 25, 25, 45]


def _read_rounds_text(path):
    with open(os.path.join(path, "rounds.jsonl"), "r", encoding="utf-8") as fh:
        return fh.read()


def test_same_seed_reproduces_logs_byte_for_byte():
    run = _run_config("random", messages=True, punishment=True)
    with tempfile.TemporaryDirectory() as d1, tempfile.TemporaryDirectory() as d2:
        run_game(run, "g0", 1234, d1, agent_kind="mock")
        run_game(run, "g0", 1234, d2, agent_kind="mock")
        t1 = _read_rounds_text(os.path.join(d1, "g0"))
        t2 = _read_rounds_text(os.path.join(d2, "g0"))
        assert t1 == t2  # rounds.jsonl identical (no timestamps in it)


def test_summary_has_metrics_and_ranks():
    run = _run_config("titfortat", messages=True, punishment=True)
    with tempfile.TemporaryDirectory() as d:
        summary = run_game(run, "g0", 1234, d, agent_kind="mock")
        assert "metrics" in summary
        assert "final_outcomes" in summary["metrics"]
        assert set(summary["scores"].keys()) == {"P1", "P2", "P3", "P4", "P5"}
        # summary.json is on disk and parseable
        with open(os.path.join(d, "g0", "summary.json")) as fh:
            json.load(fh)
