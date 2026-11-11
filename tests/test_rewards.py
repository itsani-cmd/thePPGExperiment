"""Reward phase: spend tokens to give tokens to one other player."""

from __future__ import annotations

from pgg.config import GameConfig
from pgg.prompts import builder
from tests.support import contribute, make_game, play


def test_reward_transfers_tokens_using_the_ratio():
    g = make_game(reward_enabled=True, reward_ratio=2)
    contribute(g, [10] * 5)
    before = dict(g.balances)
    g.submit_reward("P1", "P2", 4)
    g.resolve_rewards()
    assert g.balances["P1"] == before["P1"] - 4
    assert g.balances["P2"] == before["P2"] + 8
    assert g._rec.rewards[0].gain == 8


def test_invalid_rewards_become_noops_and_spend_is_clamped():
    g = make_game(reward_enabled=True, reward_max_spend=5)
    contribute(g, [10] * 5)
    assert g.submit_reward("P1", "P1", 3).spend == 0  # self
    assert g.submit_reward("P2", "P9", 3).spend == 0  # unknown seat
    assert g.submit_reward("P3", "P4", 99).spend == 5  # clamped to the max
    assert g.submit_reward("P4", "P3", -2).spend == 0
    g.resolve_rewards()
    # 1:1 rewards only move tokens around
    assert sum(g.balances.values()) == sum(g._rec.balances_after_distribution.values())


def test_skipped_rewards_leave_balances_alone():
    g = make_game()
    contribute(g, [10] * 5)
    g.skip_rewards()
    assert g._rec.balances_after_reward == g._rec.balances_after_distribution
    assert g._rec.reward_applied is False


def test_prompt_adds_the_reward_phase_only_when_enabled():
    off = builder.build_system_prompt(GameConfig(), "P1", "", "h")
    assert "Reward" not in off and "4. Punishment" in off
    on = builder.build_system_prompt(GameConfig(reward_enabled=True), "P1", "", "h")
    assert "4. Reward" in on and "5. Punishment" in on


def test_end_to_end_is_deterministic_and_conserves_tokens():
    summary, rounds = play(["random"] * 5, reward_enabled=True)
    assert rounds == play(["random"] * 5, reward_enabled=True)[1]
    assert any(x["spend"] > 0 and x["target"] for r in rounds for x in r["rewards"])
    assert summary["metrics"]["rewards"]["reward_actions"] > 0
    for r in rounds:
        assert sum(r["balances_after_reward"].values()) == sum(
            r["balances_after_distribution"].values()
        )
