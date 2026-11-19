"""Protect the horizon treatment from punishment confounds and prompt leakage."""

from pathlib import Path

from pgg.config import load_run_config
from pgg.prompts.builder import horizon_text
from pgg.runner import run_game

ROOT = Path(__file__).resolve().parents[1]


def test_v1_arms_only_change_horizon_information():
    known = load_run_config(str(ROOT / "configs/v1_known_end.yaml"))
    unknown = load_run_config(str(ROOT / "configs/v1_unknown_end.yaml"))
    excluded = {"horizon", "announce_final_round_rules"}
    assert known.game.model_dump(exclude=excluded) == unknown.game.model_dump(exclude=excluded)
    assert known.game.punishment_in_final_round
    assert known.seats == unknown.seats
    assert known.models == unknown.models


def test_unknown_end_prompt_discloses_probability_not_actual_end():
    cfg = load_run_config(str(ROOT / "configs/v1_unknown_end.yaml")).game
    ordinary = horizon_text(cfg, cfg.announce_final_round_rules, False)
    final = horizon_text(cfg, cfg.announce_final_round_rules, True)
    assert "90%" in final
    assert ordinary == final
    assert "FINAL" not in final
    assert "30" not in final


def test_both_arms_execute_final_punishment(tmp_path):
    import json

    for arm in ("known", "unknown"):
        run = load_run_config(str(ROOT / f"configs/v1_{arm}_end.yaml"))
        run_game(run, arm, run.seed, str(tmp_path), agent_kind="mock")
        rounds = [json.loads(line) for line in (tmp_path / arm / "rounds.jsonl").read_text().splitlines()]
        assert rounds
        assert all(r["punishment_applied"] for r in rounds)
