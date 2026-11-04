"""Persona loader, config loading, and dry-run call counting."""

from __future__ import annotations

import os

from pgg.config import load_run_config
from pgg.prompts.persona_loader import load_personas, parse_personas
from pgg.runner import count_calls

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_parse_personas_separates_fields():
    md = (
        "# Title\n\n"
        "## persona: maximizer\n\n"
        'principal_instruction: "Maximize my tokens."\n\n'
        "disposition: Calculating and self-interested.\n\n"
        "## persona: principal_fair\n\n"
        'principal_instruction: "Be fair."\n\n'
        "disposition:\n"
    )
    personas = parse_personas(md)
    assert personas["maximizer"].principal_instruction == "Maximize my tokens."
    assert personas["maximizer"].disposition.startswith("Calculating")
    assert personas["principal_fair"].principal_instruction == "Be fair."
    assert personas["principal_fair"].disposition == ""


def test_load_personas_from_directory():
    # one-file-per-person layout: each *.md is a persona, filename is the id,
    # README and multi-block files are handled, comment mentions don't misroute.
    personas = load_personas(os.path.join(ROOT, "personas", "defs"))
    assert sorted(personas.keys()) == [
        "flaky",
        "follower",
        "good_samaritan",
        "selfish",
        "socialist",
    ]
    assert personas["selfish"].principal_instruction.startswith("Maximize my own tokens")
    assert personas["good_samaritan"].disposition.startswith("Generous")


def test_v3_principal_blocks_in_single_file():
    # PERSONAS.md holds the Variation-3 principal-only blocks the v3 configs use.
    personas = load_personas(os.path.join(ROOT, "personas", "PERSONAS.md"))
    for pid in ("principal_selfish", "principal_socialist"):
        assert pid in personas, pid
        assert personas[pid].disposition == ""  # principal-only, no disposition
    assert "Maximize my own tokens" in personas["principal_selfish"].principal_instruction


def test_load_all_config_presets():
    cfg_dir = os.path.join(ROOT, "configs")
    for name in os.listdir(cfg_dir):
        if name.endswith(".yaml"):
            run = load_run_config(os.path.join(cfg_dir, name))
            assert len(run.seats) == run.game.n_players


def test_dry_run_counts():
    run = load_run_config(os.path.join(ROOT, "configs", "baseline.yaml"))
    est = count_calls(run, games=20)
    # 20 games x 10 rounds x 5 players x 3 phases
    assert est["total_calls"] == 20 * 10 * 5 * 3
    assert est["phases_per_round"] == 3


def test_dry_run_counts_messages_off():
    run = load_run_config(os.path.join(ROOT, "configs", "v2_comm_off.yaml"))
    est = count_calls(run, games=20)
    # messages off removes one third -> 2 phases
    assert est["phases_per_round"] == 2
    assert est["total_calls"] == 20 * 10 * 5 * 2
