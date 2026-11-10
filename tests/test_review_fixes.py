"""Exit-aware metrics, anonymity leaks, final-round rewards and related prompt/estimate fixes."""

from __future__ import annotations

from pgg.agents.base import Observation
from pgg.agents.mock_agents import TitForTat
from pgg.config import AgentSeatConfig, GameConfig
from pgg.health import persona_fidelity, run_health
from pgg.metrics import contribution_by_round, free_rider_rate, reward_stats
from pgg.prompts import builder
from pgg.runner import _make_obs, count_calls
from tests.support import SEATS, contribute, finish_round, make_game, run_config


def _round(contribs, exited=(), rewards=(), n=1):
    return {
        "round": n,
        "contributions": dict(contribs),
        "balances_before_contribution": {s: 20 for s in contribs},
        "exited": list(exited),
        "rewards": list(rewards),
        "reward_applied": bool(rewards),
        "contribution_fallbacks": {},
        "punishments": [],
        "messages": [],
    }


# --- metrics / health skip exited seats ------------------------------------ #
def test_free_rider_rate_ignores_exited_seats():
    r = _round({"P1": 10, "P2": 10, "P3": 0}, exited=["P3"])
    assert free_rider_rate([r], ["P1", "P2", "P3"], 0.25)["zero"] == 0.0


def test_contribution_fraction_is_none_for_exited_seat():
    r = _round({"P1": 10, "P2": 0}, exited=["P2"])
    frac = contribution_by_round([r], ["P1", "P2"])["fraction"][1]
    assert frac["P1"] == 0.5 and frac["P2"] is None


def test_reward_median_excludes_exiters():
    # without P4/P5 (exited, 0) the median of {10, 4, 4} is 4; P2 (10) is above it
    gift = {"giver": "P1", "target": "P2", "spend": 1, "gain": 1}
    r = _round({"P1": 4, "P2": 10, "P3": 4, "P4": 0, "P5": 0}, exited=["P4", "P5"], rewards=[gift])
    assert reward_stats([r], list(r["contributions"]))["to_high_contributor_rate"] == 1.0


def test_persona_zero_rate_excludes_exited_rounds():
    rounds = [_round({"P1": 5}, exited=[], n=1), _round({"P1": 0}, exited=["P1"], n=2)]
    for r in rounds:
        r["balances_after_punishment"] = {"P1": 20}
    rep = persona_fidelity({"rounds": rounds, "persona_of": {"P1": "x"}})
    assert rep["P1"]["zero_rate"] == 0.0


def test_reward_fallbacks_count_in_run_health():
    r = _round({"P1": 5, "P2": 5})
    r["rewards"] = [
        {"giver": "P1", "target": None, "spend": 0, "fallback_used": True},
        {"giver": "P2", "target": None, "spend": 0, "fallback_used": False},
    ]
    h = run_health({"rounds": [r], "calls": [], "persona_of": {"P1": "a", "P2": "b"}, "finished": True})
    # 2 contribution + 2 reward decisions, 1 fallback
    assert h["fallback_rate"] == 0.25


# --- anonymity side channels ------------------------------------------------ #
def _anon_game_obs(seat):
    g = make_game(
        rounds=2,
        contributions_visible="anonymous",
        reward_enabled=True,
        exit_enabled=True,
    )
    contribute(g, [10, 10, 10, 10, 0], exits={"P5"})
    g.submit_reward("P1", "P2", 3)
    g.submit_reward("P3", "P4", 2)
    g.resolve_rewards()
    g.skip_punishment()
    g.end_round()
    g.begin_round()
    return g, _make_obs(g, seat, "contribute", True, [])


def test_anonymous_rewards_show_only_own_gifts_and_hide_the_giver():
    _, giver = _anon_game_obs("P1")
    assert [(x["giver"], x["target"]) for x in giver.history[0].rewards] == [("P1", "P2")]
    _, target = _anon_game_obs("P2")
    assert [(x["giver"], x["target"]) for x in target.history[0].rewards] == [("someone", "P2")]
    _, bystander = _anon_game_obs("P5")
    assert bystander.history[0].rewards == []


def test_anonymous_exit_visible_only_to_the_exiter():
    _, other = _anon_game_obs("P1")
    assert other.history[0].exited == []
    _, leaver = _anon_game_obs("P5")
    assert leaver.history[0].exited == ["P5"]


def test_anonymous_observation_balances_only_own():
    g, obs = _anon_game_obs("P1")
    assert obs.balances == {"P1": g.balances["P1"]}


def test_named_observation_keeps_all_balances_and_gifts():
    g = make_game(rounds=2, reward_enabled=True)
    contribute(g, [10] * 5)
    g.submit_reward("P1", "P2", 3)
    g.resolve_rewards()
    g.skip_punishment()
    g.end_round()
    g.begin_round()
    obs = _make_obs(g, "P3", "contribute", True, [])
    assert set(obs.balances) == set(SEATS)
    assert obs.history[0].rewards[0]["giver"] == "P1"


# --- final-round rewards ---------------------------------------------------- #
def test_reward_in_final_round_flag_gates_the_phase():
    g = make_game(rounds=1, reward_enabled=True, reward_in_final_round=False)
    assert g.is_final_round() and not g.reward_active()
    g = make_game(rounds=1, reward_enabled=True)
    assert g.reward_active()
    g = make_game(rounds=2, reward_enabled=True, reward_in_final_round=False)
    assert not g.is_final_round() and g.reward_active()


def test_final_round_text_names_only_skipped_enabled_phases():
    both = GameConfig(reward_enabled=True, reward_in_final_round=False, punishment_in_final_round=False)
    assert "no reward or punishment phase" in builder.horizon_text(both, True, True)
    only_pun = GameConfig(punishment_in_final_round=False)
    text = builder.horizon_text(only_pun, True, True)
    assert "no punishment phase" in text and "reward" not in text
    assert "phase" not in builder.horizon_text(GameConfig(), True, True)


# --- prompt / estimate / mock ------------------------------------------------ #
def test_system_prompt_split_text_tracks_exit():
    on = builder.build_system_prompt(GameConfig(exit_enabled=True), "P1", "", "h")
    off = builder.build_system_prompt(GameConfig(), "P1", "", "h")
    assert "split equally among the players who did not exit" in on
    assert "split equally among all 5 players" in off


def test_count_calls_drops_final_round_punishment():
    seats = [AgentSeatConfig(agent_type="cooperate") for _ in range(5)]
    base = count_calls(run_config(seats, rounds=4, punishment_enabled=True), games=1)
    skip = count_calls(
        run_config(seats, rounds=4, punishment_enabled=True, punishment_in_final_round=False), games=1
    )
    assert base["action_calls"] - skip["action_calls"] == 5


def test_titfortat_anonymous_mean_ignores_the_other_exiter():
    from pgg.agents.base import RoundPublic

    # P1 saw: itself 10, group total 30, P2 exited -> other three? 5 players, 4 others, 1 exited
    last = RoundPublic(
        round=1, contributions={"P1": 10}, total_contributed=30, exited=[],
    )
    obs = Observation(
        seat="P1", seat_labels=SEATS, round=2, phase="contribute", balances={"P1": 20},
        own_balance=20, history=[last], horizon_text="",
    )
    # others contributed 20 over 4 players (exit not visible under anonymity) -> 5
    assert TitForTat("P1").contribute(obs).contribution == 5
    last.exited = ["P2"]  # an exit the viewer does know about: 20 over 3 players
    assert TitForTat("P1").contribute(obs).contribution == 7
