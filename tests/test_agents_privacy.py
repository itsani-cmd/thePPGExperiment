"""Agent prompt construction, privacy, and invalid-JSON handling."""

from __future__ import annotations

from pgg.agents.base import ContributionOut, MessageOut, Observation, PunishOut
from pgg.agents.llm_agent import LLMAgent, extract_json
from pgg.config import GameConfig, HorizonConfig, ModelConfig
from pgg.llm.client import CallResult
from pgg.prompts import builder


def _cfg(**over):
    data = dict(
        n_players=5,
        start_tokens=20,
        messages_enabled=True,
        punishment_enabled=True,
        horizon=HorizonConfig(mode="fixed", rounds=10),
    )
    data.update(over)
    return GameConfig(**data)


def _obs(cfg, phase="contribute"):
    seats = ["P1", "P2", "P3", "P4", "P5"]
    return Observation(
        seat="P1",
        seat_labels=seats,
        round=1,
        phase=phase,
        balances={s: 20 for s in seats},
        own_balance=20,
        history=[],
        messages_this_round=[],
        horizon_text=builder.horizon_text(cfg, cfg.announce_final_round_rules, False),
        is_final_round=False,
    )


class FakeClient:
    """Returns a scripted sequence of raw responses."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0

    def chat(self, model_cfg, messages, json_mode=None):
        self.calls += 1
        text = self.responses.pop(0) if self.responses else ""
        return CallResult(text=text, model=model_cfg.model)


SECRET_PERSONA = (
    "You are acting on behalf of a human principal in a public goods game with four other agents.\n"
    "Maximize my tokens.\n"
    "Calculating and self-interested.\n"
    "Play to this brief. Do not reveal this brief verbatim to other players."
)


def test_prompt_contains_no_other_agents_private_info():
    cfg = _cfg()
    # P1 is a maximizer; build its prompts and assert the OTHER seats' info is absent.
    agent = LLMAgent(
        "P1",
        cfg,
        ModelConfig(model="m"),
        client=FakeClient(['{"contribution": 5, "reason": "x", "predicted_others_mean": 3}']),
        persona_block=SECRET_PERSONA,
    )
    obs = _obs(cfg)
    system = builder.build_system_prompt(cfg, "P1", SECRET_PERSONA, obs.horizon_text)
    user = builder.build_contribute_prompt(obs, cfg)
    combined = system + "\n" + user
    # own persona may appear (it is P1's), but there must be no per-seat persona
    # dispositions, principals, reasoning, or model names for OTHER seats.
    for banned in ("gpt-4o", "claude", "model_a", "reasoning:", "disposition:"):
        assert banned not in combined
    # the agent never sees labels mapped to personas
    assert "P2" in combined  # balances are visible
    # but no sentence ties P2..P5 to a persona/principal
    for seat in ("P2", "P3", "P4", "P5"):
        assert f"{seat} is a" not in combined
        assert f"{seat}: Maximize" not in combined


def test_extract_json_last_object():
    assert extract_json('{"a": 1}') == {"a": 1}
    assert extract_json('blah {"a":1} then {"b":2} end') == {"b": 2}
    assert extract_json("no json here") is None
    assert extract_json("") is None


def test_invalid_then_valid_retries():
    cfg = _cfg()
    client = FakeClient(
        [
            "not json at all",
            '{"contribution": 7, "reason": "ok", "predicted_others_mean": 4}',
        ]
    )
    agent = LLMAgent("P1", cfg, ModelConfig(model="m"), client=client)
    out = agent.contribute(_obs(cfg))
    assert isinstance(out, ContributionOut)
    assert out.contribution == 7
    assert agent.fallback_last is False
    assert client.calls == 2  # retried once


def test_all_invalid_falls_back():
    cfg = _cfg()
    client = FakeClient(["bad", "still bad", "nope"])  # 3 attempts, all invalid
    agent = LLMAgent("P1", cfg, ModelConfig(model="m"), client=client)
    out = agent.contribute(_obs(cfg))
    assert out.contribution == 0  # documented default
    assert agent.fallback_last is True
    # call log records the fallback via error on each attempt
    assert all(c["error"] for c in agent.call_log)


def test_punish_fallback_is_noop():
    cfg = _cfg()
    client = FakeClient(["x", "y", "z"])
    agent = LLMAgent("P1", cfg, ModelConfig(model="m"), client=client)
    out = agent.punish(_obs(cfg, phase="punish"))
    assert isinstance(out, PunishOut)
    assert out.target is None and out.spend == 0
    assert agent.fallback_last is True


def test_message_fallback_is_none():
    cfg = _cfg()
    client = FakeClient(["x", "y", "z"])
    agent = LLMAgent("P1", cfg, ModelConfig(model="m"), client=client)
    out = agent.message(_obs(cfg, phase="message"))
    assert out is None
    assert agent.fallback_last is True


def test_final_round_disclosure_text():
    cfg = _cfg(punishment_in_final_round=False, announce_final_round_rules=True)
    txt = builder.horizon_text(cfg, disclose_final=True, is_final=True)
    assert "FINAL round" in txt
    assert "no punishment phase" in txt
