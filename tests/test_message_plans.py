"""Message-phase survey (intent, claimed/intended contribution) is parsed leniently,
logged per round under ``message_plans``, and never shown to other agents."""

from __future__ import annotations

import json
import os
import tempfile

from pgg.agents.base import MessageOut
from pgg.agents.mock_agents import _MockBase
from pgg.config import AgentSeatConfig, GameConfig, HorizonConfig, ModelConfig, RunConfig
from pgg.prompts import builder
from pgg.runner import _make_obs, run_game


def test_survey_fields_parse_and_bad_values_never_fail_the_reply():
    out = MessageOut(
        message="hi",
        intent="propose_norm</intent>",
        claimed_contribution="10",
        intended_contribution=7.0,
    )
    assert (out.intent, out.claimed_contribution, out.intended_contribution) == ("propose_norm", 10, 7)

    bad = MessageOut(message="hi", intent=3, claimed_contribution="none", intended_contribution=True)
    assert (bad.intent, bad.claimed_contribution, bad.intended_contribution) == (None, None, None)

    # old-style reply without the survey still works
    assert MessageOut(message="hi").plan()["claimed_contribution"] is None


def _play_with_plans(monkeypatch, message_mode="sequential", contributions_visible="named"):
    def message(self, obs):
        if obs.seat == "P5":  # stays silent but still records a private plan
            return MessageOut(message="", intent="silent", intended_contribution=0)
        return MessageOut(
            message=f"{obs.seat} will give 10",
            intent="deceive",
            claimed_contribution=10,
            intended_contribution=2,
        )

    monkeypatch.setattr(_MockBase, "message", message)
    run = RunConfig(
        name="t",
        seed=11,
        games=1,
        game=GameConfig(
            messages_enabled=True,
            message_mode=message_mode,
            contributions_visible=contributions_visible,
            horizon=HorizonConfig(mode="fixed", rounds=2),
        ),
        seats=[AgentSeatConfig(agent_type="cooperate") for _ in range(5)],
        models={"m": ModelConfig(model="mock")},
    )
    out_dir = tempfile.mkdtemp()
    run_game(run, "g0", 11, out_dir, agent_kind="mock")
    with open(os.path.join(out_dir, "g0", "rounds.jsonl")) as f:
        return [json.loads(line) for line in f if line.strip()]


def test_plans_are_logged_for_every_seat_including_silent_ones(monkeypatch):
    for mode in ("sequential", "simultaneous"):
        rounds = _play_with_plans(monkeypatch, message_mode=mode)
        plans = rounds[0]["message_plans"]
        assert set(plans) == {"P1", "P2", "P3", "P4", "P5"}
        assert plans["P1"] == {
            "intent": "deceive",
            "claimed_contribution": 10,
            "intended_contribution": 2,
            "sent_message": True,
        }
        assert plans["P5"]["sent_message"] is False
        assert plans["P5"]["intended_contribution"] == 0


def test_plans_never_reach_other_agents_prompts(monkeypatch):
    from pgg.engine import Game

    rounds = _play_with_plans(monkeypatch, contributions_visible="anonymous")
    assert rounds[0]["message_plans"]["P1"]["intent"] == "deceive"

    # Rebuild a later-round prompt from a game whose history holds a private plan.
    cfg = GameConfig(messages_enabled=True, horizon=HorizonConfig(mode="fixed", rounds=2))
    g = Game(cfg, ["P1", "P2", "P3", "P4", "P5"], seed=1)
    rec = g.begin_round()
    g.submit_message("P1", "P1 will give 10")
    rec.message_plans["P1"] = {"intent": "deceive", "claimed_contribution": 10, "intended_contribution": 2}
    g.close_messages()
    for s in ["P1", "P2", "P3", "P4", "P5"]:
        g.submit_contribution(s, 5)
    g.resolve_contributions_and_distribution()
    g.skip_rewards()
    g.skip_punishment()
    g.end_round()
    g.begin_round()
    text = builder.build_contribute_prompt(_make_obs(g, "P2", "contribute", True, []), cfg)
    assert "P1 will give 10" in text  # the public message is visible
    assert "deceive" not in text and "intended" not in text


def test_do_nothing_punish_reply_with_null_text_fields_is_valid():
    from pgg.agents.base import PunishOut

    out = PunishOut(target=None, spend=0, motive="avoid_cost", reason=None, expected_effect=None)
    assert (out.target, out.spend, out.reason, out.expected_effect) == (None, 0, "", "")
