"""V5 punishment visibility options (``punishments_visible``): public, private, hidden.

Round 1: P1 punishes P2, P3 punishes P1. P4 is a bystander.
"""

from __future__ import annotations

import pytest

from pgg.config import GameConfig
from pgg.prompts import builder
from pgg.runner import _make_obs
from tests.support import contribute, make_game


def _seen(seat, **game_kw):
    g = make_game(rounds=2, contributions_visible="anonymous", **game_kw)
    contribute(g, [10, 0, 10, 10, 10])
    g.skip_rewards()
    g.submit_punishment("P1", "P2", 2)
    g.submit_punishment("P3", "P1", 1)
    g.resolve_punishment()
    g.end_round()
    g.begin_round()
    obs = _make_obs(g, seat, "contribute", True, [])
    return [(p["punisher"], p["target"]) for p in obs.history[0].punishments], obs, g.cfg


def test_default_anonymous_is_private_like_before():
    assert GameConfig(contributions_visible="anonymous").punishment_visibility == "private"
    assert GameConfig().punishment_visibility == "public"
    assert _seen("P1")[0] == [("P1", "P2"), ("someone", "P1")]


def test_private_shows_given_and_received_with_the_punisher_hidden():
    vis = {"punishments_visible": "private"}
    assert _seen("P1", **vis)[0] == [("P1", "P2"), ("someone", "P1")]
    assert _seen("P2", **vis)[0] == [("someone", "P2")]
    assert _seen("P4", **vis)[0] == []


def test_public_shows_every_punishment_to_everyone():
    for seat in ("P1", "P2", "P4"):
        pairs, obs, cfg = _seen(seat, punishments_visible="public")
        assert pairs == [("P1", "P2"), ("P3", "P1")]
        text = builder.build_contribute_prompt(obs, cfg)
        assert "punish P3 -> P1" in text
        # contributions stay anonymous
        assert obs.history[0].contributions == {seat: obs.history[0].contributions[seat]}


def test_hidden_shows_only_punishments_you_gave():
    vis = {"punishments_visible": "hidden"}
    assert _seen("P1", **vis)[0] == [("P1", "P2")]
    assert _seen("P2", **vis)[0] == []
    _, obs, cfg = _seen("P2", **vis)
    assert "  punish " not in builder.build_contribute_prompt(obs, cfg)


def test_rule_sentence_only_when_set_explicitly():
    base = builder.build_system_prompt(GameConfig(contributions_visible="anonymous"), "P1", "", "h")
    assert "Punishments are" not in base  # old configs render exactly as before
    for mode in ("public", "private", "hidden"):
        cfg = GameConfig(contributions_visible="anonymous", punishments_visible=mode)
        text = builder.build_system_prompt(cfg, "P1", "", "h")
        assert builder.PUNISHMENT_VISIBILITY_RULES[mode] in text


def test_rewards_are_unaffected_by_punishment_visibility():
    g = make_game(rounds=2, contributions_visible="anonymous", reward_enabled=True,
                  punishments_visible="public")
    contribute(g, [10, 10, 10, 10, 10])
    g.submit_reward("P1", "P2", 3)
    g.resolve_rewards()
    g.skip_punishment()
    g.end_round()
    g.begin_round()
    assert _make_obs(g, "P4", "contribute", True, []).history[0].rewards == []


def test_bad_value_is_rejected():
    with pytest.raises(ValueError):
        GameConfig(punishments_visible="everyone")
