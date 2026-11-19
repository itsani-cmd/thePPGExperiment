"""Validate the late-game estimand and game-level missing-data behavior."""
import importlib.util
from pathlib import Path

SPEC = importlib.util.spec_from_file_location('v1_analysis', Path(__file__).resolve().parents[1]/'scripts/analyze_variation1.py')
a = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(a)


def test_bootstrap_does_not_create_precision_for_one_game():
    assert a.estimate([None]) == {'n': 0, 'mean': None, 'ci95': None}
    assert a.estimate([0.5, None]) == {'n': 1, 'mean': 0.5, 'ci95': None}
    assert a.estimate([0.25]*3)['ci95'] == [0.25, 0.25]


def test_late_game_change_is_missing_for_short_games(tmp_path):
    from pgg.config import load_run_config
    from pgg.runner import run_game
    import json
    root = Path(__file__).resolve().parents[1]
    run = load_run_config(str(root/'configs/v1_known_end.yaml'))
    run.game.horizon.rounds = 2
    run_game(run, 'short', 1, str(tmp_path), agent_kind='mock')
    # describe's relative path is rooted at the repo for portable JSON outputs.
    previous = a.ROOT
    try:
        a.ROOT = tmp_path
        result = a.describe(tmp_path/'short')
    finally:
        a.ROOT = previous
    assert result['round10_change'] is None
    assert result['realized_end_change'] is None
    assert result['rounds'] == 2


def test_round10_change_uses_rounds_seven_to_nine(tmp_path):
    from pgg.config import load_run_config
    from pgg.runner import run_game
    import json
    root = Path(__file__).resolve().parents[1]
    run = load_run_config(str(root/'configs/v1_known_end.yaml'))
    run_game(run, 'long', 1, str(tmp_path), agent_kind='mock')
    p = tmp_path/'long/rounds.jsonl'
    rounds = [json.loads(line) for line in p.read_text().splitlines()]
    for r in rounds:
        r['balances_before_contribution'] = {s:20 for s in r['contributions']}
        amount = 10 if r['round'] in (7,8,9) else 20
        if r['round'] == 10:
            amount = 0
        r['contributions'] = {s:amount for s in r['contributions']}
    p.write_text('\n'.join(json.dumps(r) for r in rounds))
    previous = a.ROOT
    try:
        a.ROOT = tmp_path
        assert a.describe(tmp_path/'long')['round10_change'] == -0.5
    finally:
        a.ROOT = previous
