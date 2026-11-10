"""Exit option: sit a round out for a fixed payoff."""

from __future__ import annotations

from pgg.config import GameConfig
from pgg.engine import resolve_distribution
from pgg.prompts import builder
from tests.support import SEATS, contribute, make_game, play


def test_exit_pays_fixed_amount_and_splits_among_active():
    g = make_game(exit_enabled=True, exit_payoff=2)
    contribute(g, [10, 10, 10, 10, 20], exits={"P5"})
    rec = g._rec
    assert rec.exited == ["P5"]
    assert rec.contributions["P5"] == 0
    # fund = 40 * 1.6 = 64, split over the 4 players who stayed
    assert rec.pot == 64 and rec.share == 16 and rec.carry_out == 0
    assert g.balances["P1"] == 20 - 10 + 16
    assert g.balances["P5"] == 20 + 2  # kept everything, got the payoff, no share


def test_exit_is_ignored_when_the_option_is_off():
    g = make_game()
    contribute(g, [10] * 5, exits={"P1"})
    assert g._rec.exited == [] and g._rec.contributions["P1"] == 10


def test_everyone_exiting_does_not_crash_and_carries_the_fund():
    g = make_game(exit_enabled=True)
    contribute(g, [0] * 5, exits=SEATS)
    assert g._rec.pot == 0 and g._rec.share == 0
    assert resolve_distribution([], 3, 1.6, 0) == {"pot": 3, "share": 0, "carry_out": 3}


def test_exiter_cannot_punish_or_be_punished():
    g = make_game(exit_enabled=True)
    contribute(g, [10, 10, 10, 10, 0], exits={"P5"})
    by_exiter = g.submit_punishment("P5", "P1", 5)
    on_exiter = g.submit_punishment("P1", "P5", 5)
    assert by_exiter.spend == 0 and by_exiter.target is None
    assert on_exiter.spend == 0 and on_exiter.target is None


def test_prompt_mentions_exit_only_when_enabled():
    assert "EXIT" not in builder.build_system_prompt(GameConfig(), "P1", "", "h")
    assert "EXIT" in builder.build_system_prompt(GameConfig(exit_enabled=True), "P1", "", "h")


def test_end_to_end_with_a_leaver():
    summary, rounds = play(
        ["cooperate"] * 4 + ["leaver"], exit_enabled=True, punishment_enabled=False
    )
    for r in rounds:
        assert len(r["exited"]) == 1
        assert r["contributions"][r["exited"][0]] == 0
    assert summary["metrics"]["exits"]["exit_rate"] == 0.2


def test_exit_with_null_or_missing_contribution_parses():
    from pgg.agents.base import ContributionOut

    assert ContributionOut(contribution=None, exit=True).contribution == 0
    assert ContributionOut(exit=True).exit is True
