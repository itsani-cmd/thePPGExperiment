"""Engine tests: the exact integer math from the spec's §10 vectors."""

from __future__ import annotations

import statistics

from pgg.config import GameConfig, HorizonConfig
from pgg.engine import (
    Game,
    _cost_for_damage,
    _nominal_damage,
    _proportional_allocation,
    average_ranks,
    resolve_distribution,
)


SEATS = ["P1", "P2", "P3", "P4", "P5"]


def base_cfg(**over):
    data = dict(
        n_players=5,
        start_tokens=20,
        multiplier=1.6,
        messages_enabled=False,
        punishment_enabled=True,
        horizon=HorizonConfig(mode="fixed", rounds=10),
    )
    data.update(over)
    return GameConfig(**data)


# --------------------------------------------------------------------------- #
# Distribution
# --------------------------------------------------------------------------- #
def test_all_contribute_20_first_round():
    # fund 100, pot 160, share 32 each; final 0 + 32 = 32
    g = Game(base_cfg(), SEATS, seed=1)
    g.begin_round()
    for s in SEATS:
        g.submit_contribution(s, 20)
    g.resolve_contributions_and_distribution()
    rec = g._rec
    assert rec.pot == 160
    assert rec.share == 32
    assert rec.carry_out == 0
    for s in SEATS:
        assert g.balances[s] == 32


def test_one_defector():
    # one defects (0), four contribute 20: fund 80, pot 128, share 25, remainder 3
    g = Game(base_cfg(), SEATS, seed=1)
    g.begin_round()
    g.submit_contribution("P1", 0)
    for s in SEATS[1:]:
        g.submit_contribution(s, 20)
    g.resolve_contributions_and_distribution()
    rec = g._rec
    assert rec.pot == 128
    assert rec.share == 25
    assert rec.carry_out == 3
    assert g.balances["P1"] == 45  # 20 - 0 + 25
    for s in SEATS[1:]:
        assert g.balances[s] == 25  # 20 - 20 + 25


def test_carry_over_added_to_next_pot():
    # carry 3 from last test: next round all contribute 0 -> pot = floor(0*1.6+3)=3
    out = resolve_distribution([0, 0, 0, 0, 0], carry_in=3, multiplier=1.6, n_players=5)
    assert out["pot"] == 3
    assert out["share"] == 0
    assert out["carry_out"] == 3
    # a contribution of 10 total with carry 3: floor(16+3)=19 -> share 3 carry 4
    out2 = resolve_distribution([10, 0, 0, 0, 0], carry_in=3, multiplier=1.6, n_players=5)
    assert out2["pot"] == 19
    assert out2["share"] == 3
    assert out2["carry_out"] == 4


def test_distribution_uses_exact_rational():
    # sum = 7 -> 7 * 8/5 = 11.2 -> floor 11, not float drift
    out = resolve_distribution([7, 0, 0, 0, 0], carry_in=0, multiplier=1.6, n_players=5)
    assert out["pot"] == 11


# --------------------------------------------------------------------------- #
# Punishment math (integer rule, per PGG_REFERENCE §0)
# --------------------------------------------------------------------------- #
def test_punish_spend10_vs_45():
    cfg = base_cfg()
    assert _nominal_damage(10, 45, cfg) == 22  # min(30, floor(22.5)=22, 100)
    assert _cost_for_damage(22, cfg) == 8  # ceil(22/3)
    # refund = spend - cost = 2


def test_punish_spend10_vs_100():
    cfg = base_cfg()
    assert _nominal_damage(10, 100, cfg) == 30  # min(30, 50, 100)
    assert _cost_for_damage(30, cfg) == 10  # no refund


def test_punish_spend3_vs_25():
    cfg = base_cfg()
    # 3*3=9, cap floor(12.5)=12 not reached -> damage 9, cost 3
    assert _nominal_damage(3, 25, cfg) == 9
    assert _cost_for_damage(9, cfg) == 3


def test_punish_full_flow_refund():
    cfg = base_cfg()
    g = Game(cfg, SEATS, seed=1)
    g.begin_round()
    # set up: P1 defects to reach 45 post-dist, others 25 (reuse one-defector)
    g.submit_contribution("P1", 0)
    for s in SEATS[1:]:
        g.submit_contribution(s, 20)
    g.resolve_contributions_and_distribution()
    assert g.balances["P1"] == 45
    # P2 spends 10 on P1
    g.submit_punishment("P2", "P1", 10)
    g.resolve_punishment()
    rec = g._rec
    act = [p for p in rec.punishments if p.punisher == "P2"][0]
    assert act.damage == 22
    assert act.cost == 8
    assert act.refund == 2
    assert act.actual_damage == 22
    assert g.balances["P1"] == 45 - 22
    assert g.balances["P2"] == 25 - 8


# --------------------------------------------------------------------------- #
# Punishment validation
# --------------------------------------------------------------------------- #
def test_cannot_contribute_more_than_balance():
    g = Game(base_cfg(), SEATS, seed=1)
    g.begin_round()
    c = g.submit_contribution("P1", 999)
    assert c == 20  # clamped to balance


def test_cannot_punish_self():
    g = Game(base_cfg(), SEATS, seed=1)
    g.begin_round()
    for s in SEATS:
        g.submit_contribution(s, 0)
    g.resolve_contributions_and_distribution()
    a = g.submit_punishment("P1", "P1", 5)
    assert a.target is None and a.spend == 0


def test_cannot_spend_more_than_10_or_balance():
    cfg = base_cfg()
    g = Game(cfg, SEATS, seed=1)
    g.begin_round()
    for s in SEATS:
        g.submit_contribution(s, 0)
    g.resolve_contributions_and_distribution()  # balances back to 20 (0 contrib, share 0)
    a = g.submit_punishment("P1", "P2", 50)
    assert a.spend == 10  # capped at punish_max_spend
    # now low balance: force P3 near-empty
    g.balances["P3"] = 4
    b = g.submit_punishment("P3", "P2", 10)
    assert b.spend == 4  # capped at balance


def test_multiple_punishers_clamp_at_zero():
    cfg = base_cfg()
    g = Game(cfg, SEATS, seed=1)
    g.begin_round()
    for s in SEATS:
        g.submit_contribution(s, 0)
    g.resolve_contributions_and_distribution()
    # target P5 has 20; three punishers each spend 10 -> nominal each min(30, floor(10)=10,100)=10
    g.balances["P5"] = 20
    g.submit_punishment("P1", "P5", 10)
    g.submit_punishment("P2", "P5", 10)
    g.submit_punishment("P3", "P5", 10)
    g.resolve_punishment()
    assert g.balances["P5"] == 0
    rec = g._rec
    acts = [p for p in rec.punishments if p.target == "P5"]
    assert sum(p.actual_damage for p in acts) == 20  # clamped total == starting balance


# --------------------------------------------------------------------------- #
# Final-round punishment toggle
# --------------------------------------------------------------------------- #
def test_final_round_punishment_off():
    cfg = base_cfg(punishment_in_final_round=False, horizon=HorizonConfig(mode="fixed", rounds=1))
    g = Game(cfg, SEATS, seed=1)
    g.begin_round()
    assert g.is_final_round()
    assert g.punishment_active() is False


# --------------------------------------------------------------------------- #
# Geometric horizon
# --------------------------------------------------------------------------- #
def test_geometric_horizon_reproducible():
    cfg = base_cfg(horizon=HorizonConfig(mode="geometric", p_continue=0.9, max_rounds=30))
    g1 = Game(cfg, SEATS, seed=777)
    g2 = Game(cfg, SEATS, seed=777)
    assert g1.total_rounds == g2.total_rounds
    assert 1 <= g1.total_rounds <= 30


def test_geometric_horizon_mean_near_10():
    cfg = base_cfg(horizon=HorizonConfig(mode="geometric", p_continue=0.9, max_rounds=30))
    lengths = [Game(cfg, SEATS, seed=s).total_rounds for s in range(2000)]
    mean = statistics.mean(lengths)
    assert 8.5 <= mean <= 11.5  # expected 10 for p=0.9
    assert max(lengths) <= 30


# --------------------------------------------------------------------------- #
# Ranks + allocation utilities
# --------------------------------------------------------------------------- #
def test_average_ranks_ties():
    ranks = average_ranks({"P1": 50, "P2": 50, "P3": 10, "P4": 10, "P5": 10})
    assert ranks["P1"] == 1.5 and ranks["P2"] == 1.5  # tie for 1st/2nd
    assert ranks["P3"] == 4.0 and ranks["P4"] == 4.0 and ranks["P5"] == 4.0  # 3,4,5 avg


def test_proportional_allocation_sums_to_total():
    alloc = _proportional_allocation([10, 10, 10], 20)
    assert sum(alloc) == 20
    alloc2 = _proportional_allocation([30, 10], 20)
    assert sum(alloc2) == 20
    assert alloc2[0] >= alloc2[1]
