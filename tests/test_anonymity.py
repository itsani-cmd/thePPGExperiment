"""Anonymous contributions: players see only their own gift and the group total."""

from __future__ import annotations

from pgg.config import GameConfig
from pgg.prompts import builder
from pgg.runner import _make_obs
from tests.support import contribute, finish_round, make_game, play


def _second_round_observation(seat, **game_kw):
    g = make_game(rounds=2, **game_kw)
    contribute(g, [1, 2, 3, 4, 5])
    finish_round(g)
    return g.cfg, _make_obs(g, seat, "contribute", True, [])


def test_anonymous_history_hides_other_contributions_and_balances():
    cfg, obs = _second_round_observation("P3", contributions_visible="anonymous")
    h = obs.history[0]
    assert h.contributions == {"P3": 3}
    assert h.total_contributed == 15
    assert set(h.balances_after_distribution) == {"P3"}
    text = builder.build_contribute_prompt(obs, cfg)
    assert "P1=1" not in text
    assert "group total 15" in text
    assert "Current balances" not in text


def test_named_history_shows_everyone():
    cfg, obs = _second_round_observation("P3")
    assert obs.history[0].contributions == {"P1": 1, "P2": 2, "P3": 3, "P4": 4, "P5": 5}
    assert "P1=1, P2=2, P3=3, P4=4, P5=5" in builder.build_contribute_prompt(obs, cfg)


def test_system_prompt_says_contributions_are_anonymous_only_when_enabled():
    named = builder.build_system_prompt(GameConfig(), "P1", "", "h")
    anon = builder.build_system_prompt(GameConfig(contributions_visible="anonymous"), "P1", "", "h")
    assert "anonymous" not in named
    assert "anonymous" in anon


def test_tit_for_tat_plays_the_same_with_only_the_total_visible():
    # Its "others' mean" can be recovered from the group total, so hiding who gave
    # what must not change its behavior.
    _, named = play(["titfortat"] * 5)
    _, anon = play(["titfortat"] * 5, contributions_visible="anonymous")
    assert [r["contributions"] for r in named] == [r["contributions"] for r in anon]
