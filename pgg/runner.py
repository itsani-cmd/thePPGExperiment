"""Drive games: build agents, step the engine through phases, log, resume.

The runner owns everything the engine deliberately excludes: seat/persona/model
assignment (seeded, logged), building observations from the public log, calling
agents (concurrently within a phase, phases sequential), and writing JSONL.

Determinism contract: with mock agents, the same ``seed`` reproduces identical
rounds.jsonl byte-for-byte (timestamps live only in config.json/summary.json).
"""

from __future__ import annotations

import concurrent.futures
import dataclasses
import os
import random
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from .agents.base import (
    ContributionOut,
    MessageView,
    Observation,
    RoundPublic,
)
from .agents.mock_agents import make_mock
from .config import ModelConfig, RunConfig
from .engine import Game, RoundRecord, stable_seed
from .llm.client import LLMClient
from .logging_ import GameLogger, git_hash, now_iso
from .prompts import builder
from .prompts.persona_loader import load_personas


# --------------------------------------------------------------------------- #
# Seat assignment
# --------------------------------------------------------------------------- #
@dataclasses.dataclass
class SeatAssignment:
    seat: str
    persona: Optional[str]
    principal: Optional[str]
    model: Optional[str]
    agent_type: Optional[str]
    persona_block: str = ""


def seat_labels(n: int) -> List[str]:
    return [f"P{i + 1}" for i in range(n)]


def assign_seats(
    run: RunConfig, game_seed: int, persona_dir_file: str
) -> List[SeatAssignment]:
    """Randomly map configured seat specs to seat labels using the game seed.

    The persona/principal/model lists are shuffled onto labels P1..Pn so the
    label -> identity mapping varies per game but is reproducible. The mapping is
    returned (and logged by the caller).
    """
    n = run.game.n_players
    labels = seat_labels(n)
    specs = list(run.seats) if run.seats else []
    if not specs:
        # baseline-style default: n null seats, model from the first configured model
        from .config import AgentSeatConfig

        default_model = next(iter(run.models), None)
        specs = [AgentSeatConfig(model=default_model) for _ in range(n)]

    rng = random.Random(stable_seed(game_seed, "seatassign"))
    order = list(range(n))
    rng.shuffle(order)

    personas = load_personas(persona_dir_file)
    template = _persona_template()

    assignments: List[SeatAssignment] = []
    for label_idx, spec_idx in enumerate(order):
        spec = specs[spec_idx]
        block = _render_persona_block(spec, personas, template)
        assignments.append(
            SeatAssignment(
                seat=labels[label_idx],
                persona=spec.persona,
                principal=spec.principal,
                model=spec.model,
                agent_type=spec.agent_type,
                persona_block=block,
            )
        )
    assignments.sort(key=lambda a: a.seat)
    return assignments


def _persona_template() -> str:
    path = os.path.join(os.path.dirname(__file__), "prompts", "persona_template.md")
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


def _render_persona_block(spec, personas, template) -> str:
    """Compose the persona system block for a seat.

    ``principal`` (if set) supplies the principal_instruction; ``persona`` (if
    set) supplies the disposition. Variation 3 sets only ``principal``.
    """
    if not spec.persona and not spec.principal:
        return ""
    principal_text = ""
    disposition_text = ""
    if spec.principal and spec.principal in personas:
        principal_text = personas[spec.principal].principal_instruction
    if spec.persona and spec.persona in personas:
        p = personas[spec.persona]
        disposition_text = p.disposition
        if not principal_text:
            principal_text = p.principal_instruction
    return template.format(
        principal_instruction=principal_text,
        disposition=disposition_text,
    ).strip()


# --------------------------------------------------------------------------- #
# Agent construction
# --------------------------------------------------------------------------- #
def build_agents(
    run: RunConfig,
    assignments: Sequence[SeatAssignment],
    agent_kind: str,
    client: Optional[LLMClient],
    game_seed: int,
) -> Dict[str, object]:
    """Return {seat: agent}. ``agent_kind`` is 'mock' or 'llm'."""
    agents: Dict[str, object] = {}
    for a in assignments:
        if agent_kind == "mock":
            atype = a.agent_type or "cooperate"
            agents[a.seat] = make_mock(atype, seed=stable_seed(game_seed, a.seat))
        else:
            from .agents.llm_agent import LLMAgent

            model_name = a.model or next(iter(run.models), None)
            if model_name is None or model_name not in run.models:
                raise ValueError(
                    f"seat {a.seat} references model '{model_name}' not in config.models"
                )
            model_cfg = run.models[model_name]
            assert client is not None
            agents[a.seat] = LLMAgent(
                seat=a.seat,
                cfg=run.game,
                model_cfg=model_cfg,
                client=client,
                persona_block=a.persona_block,
            )
    return agents


# --------------------------------------------------------------------------- #
# Observation building (from the engine's public state)
# --------------------------------------------------------------------------- #
def _public_history(game: Game) -> List[RoundPublic]:
    out: List[RoundPublic] = []
    for rec in game.history:
        out.append(
            RoundPublic(
                round=rec.round,
                speaker_order=list(rec.speaker_order),
                messages=[MessageView(seat=m.seat, text=m.text) for m in rec.messages],
                contributions=dict(rec.contributions),
                share=rec.share,
                pot=rec.pot,
                balances_after_distribution=dict(rec.balances_after_distribution),
                punishments=[
                    {
                        "punisher": p.punisher,
                        "target": p.target,
                        "spend": p.spend,
                        "actual_damage": p.actual_damage,
                    }
                    for p in rec.punishments
                    if p.target is not None and p.spend > 0
                ],
                balances_after_punishment=dict(rec.balances_after_punishment),
            )
        )
    return out


def _make_obs(
    game: Game,
    seat: str,
    phase: str,
    disclose_final: bool,
    messages_this_round: List[MessageView],
    this_round_contributions: Optional[Dict[str, int]] = None,
    this_round_share: Optional[int] = None,
) -> Observation:
    cfg = game.cfg
    is_final = game.is_final_round()
    return Observation(
        seat=seat,
        seat_labels=list(game.seats),
        round=game.round,
        phase=phase,
        balances=dict(game.balances),
        own_balance=game.balances[seat],
        history=_public_history(game),
        messages_this_round=list(messages_this_round),
        this_round_contributions=this_round_contributions,
        this_round_share=this_round_share,
        horizon_text=builder.horizon_text(
            cfg, cfg.announce_final_round_rules, is_final
        ),
        is_final_round=is_final,
    )


# --------------------------------------------------------------------------- #
# Concurrency helper
# --------------------------------------------------------------------------- #
def _run_phase_concurrent(
    seats: List[str],
    fn: Callable[[str], object],
    workers: int,
) -> Dict[str, object]:
    """Call ``fn(seat)`` for each seat; parallel for LLM, ordered result dict."""
    if workers <= 1 or len(seats) <= 1:
        return {s: fn(s) for s in seats}
    results: Dict[str, object] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
        futures = {ex.submit(fn, s): s for s in seats}
        for fut in concurrent.futures.as_completed(futures):
            s = futures[fut]
            results[s] = fut.result()
    return {s: results[s] for s in seats}  # restore seat order


# --------------------------------------------------------------------------- #
# One game
# --------------------------------------------------------------------------- #
def run_game(
    run: RunConfig,
    game_id: str,
    game_seed: int,
    run_dir: str,
    agent_kind: str = "mock",
    client: Optional[LLMClient] = None,
    phase_workers: int = 1,
    on_event: Optional[Callable[[str, Dict[str, object]], None]] = None,
) -> Dict[str, object]:
    """Play one game to completion and write its logs. Returns the summary dict.

    ``on_event(kind, data)`` is an optional display hook, called with
    ``("start", ...)``, ``("round", ...)`` and ``("end", ...)``. It never affects
    the game or the logs.
    """
    from .metrics import game_metrics  # local import to avoid cycle

    logger = GameLogger(run_dir, game_id)
    if logger.is_complete():
        return _load_summary(logger)

    assignments = assign_seats(run, game_seed, run.personas_file)
    agents = build_agents(run, assignments, agent_kind, client, game_seed)
    game = Game(run.game, [a.seat for a in assignments], game_seed)

    # config.json — resolved config + assignment mapping + metadata
    logger.write_config(
        {
            "run_name": run.name,
            "game_id": game_id,
            "seed": game_seed,
            "git_hash": git_hash(os.getcwd()),
            "created_at": now_iso(),
            "agent_kind": agent_kind,
            "intent_probe": run.game.intent_probe,
            "game_config": run.game.model_dump(),
            "models": {k: v.model_dump() for k, v in run.models.items()},
            "seat_assignment": [
                {
                    "seat": a.seat,
                    "persona": a.persona,
                    "principal": a.principal,
                    "model": a.model,
                    "agent_type": a.agent_type,
                }
                for a in assignments
            ],
            "sampled_total_rounds": game.total_rounds,
        }
    )

    cfg = run.game
    disclose_final = cfg.announce_final_round_rules
    who = {a.seat: (a.persona or a.principal or a.agent_type or "") for a in assignments}
    if on_event:
        on_event("start", {"game_id": game_id, "who": who, "total_rounds": game.total_rounds})

    while not game.finished:
        if on_event:
            on_event("progress", {"game_id": game_id, "text": f"round {game.round}: agents are deciding..."})
        rec = game.begin_round()
        spoken: List[MessageView] = []

        # ---- messages ---------------------------------------------------- #
        if game.messages_active():
            order = game.message_order()
            if cfg.message_mode == "sequential":
                for seat in order:
                    obs = _make_obs(game, seat, "message", disclose_final, spoken)
                    out = agents[seat].message(obs)
                    fb = getattr(agents[seat], "fallback_last", False)
                    if out is not None and out.message:
                        action = game.submit_message(
                            seat, out.message, out.norm_stated, fb
                        )
                        spoken.append(MessageView(seat=seat, text=action.text))
                    elif out is None and fb:
                        game.submit_message(seat, "", False, True)
            else:  # simultaneous
                obs_map = {
                    s: _make_obs(game, s, "message", disclose_final, [])
                    for s in order
                }
                outs = _run_phase_concurrent(
                    order, lambda s: agents[s].message(obs_map[s]), phase_workers
                )
                for seat in order:
                    out = outs[seat]
                    fb = getattr(agents[seat], "fallback_last", False)
                    if out is not None and out.message:
                        game.submit_message(seat, out.message, out.norm_stated, fb)
                    elif out is None and fb:
                        game.submit_message(seat, "", False, True)
            game.close_messages()
            spoken = [MessageView(seat=m.seat, text=m.text) for m in rec.messages]

        # ---- contributions ---------------------------------------------- #
        obs_map = {
            s: _make_obs(game, s, "contribute", disclose_final, spoken)
            for s in game.seats
        }
        contrib_outs = _run_phase_concurrent(
            list(game.seats),
            lambda s: agents[s].contribute(obs_map[s]),
            phase_workers,
        )
        for seat in game.seats:
            out: ContributionOut = contrib_outs[seat]
            fb = getattr(agents[seat], "fallback_last", False)
            game.submit_contribution(seat, out.contribution, fb)
        game.resolve_contributions_and_distribution()

        # ---- punishment -------------------------------------------------- #
        if game.punishment_active():
            this_contrib = dict(rec.contributions)
            obs_map = {
                s: _make_obs(
                    game,
                    s,
                    "punish",
                    disclose_final,
                    spoken,
                    this_round_contributions=this_contrib,
                    this_round_share=rec.share,
                )
                for s in game.seats
            }
            punish_outs = _run_phase_concurrent(
                list(game.seats),
                lambda s: agents[s].punish(obs_map[s]),
                phase_workers,
            )
            for seat in game.seats:
                out = punish_outs[seat]
                fb = getattr(agents[seat], "fallback_last", False)
                game.submit_punishment(
                    seat,
                    out.target,
                    out.spend,
                    reason=out.reason,
                    expected_effect=out.expected_effect,
                    fallback_used=fb,
                )
            game.resolve_punishment()
        else:
            game.skip_punishment()

        # ---- intent probe (optional, after actions, no feedback) --------- #
        if cfg.intent_probe and agent_kind == "llm":
            for seat in game.seats:
                obs = _make_obs(game, seat, "intent_probe", disclose_final, spoken)
                probe_fn = getattr(agents[seat], "intent_probe", None)
                if probe_fn is not None:
                    probe_fn(obs)  # logged via calls; not fed back

        # ---- persist ----------------------------------------------------- #
        game.end_round()
        round_dict = _round_to_dict(rec)
        logger.append_round(round_dict)
        if on_event:
            on_event("round", {"game_id": game_id, "who": who, "round": round_dict})
        # drain LLM call logs
        if agent_kind == "llm":
            for seat in game.seats:
                drain = getattr(agents[seat], "drain_calls", None)
                if drain is not None:
                    logger.append_calls(drain())

    summary = _build_summary(run, game_id, game_seed, game, logger)
    summary["metrics"] = game_metrics(run.game, logger.read_rounds(), game.seats)
    logger.write_summary(summary)
    if on_event:
        on_event("end", {"game_id": game_id, "who": who, "summary": summary})
    return summary


def _round_to_dict(rec: RoundRecord) -> Dict[str, object]:
    return {
        "round": rec.round,
        "speaker_order": rec.speaker_order,
        "messages": [dataclasses.asdict(m) for m in rec.messages],
        "balances_before_contribution": rec.balances_before_contribution,
        "contributions": rec.contributions,
        "contribution_fallbacks": rec.contribution_fallbacks,
        "balances_after_contribution": rec.balances_after_contribution,
        "carry_in": rec.carry_in,
        "pot": rec.pot,
        "share": rec.share,
        "carry_out": rec.carry_out,
        "balances_after_distribution": rec.balances_after_distribution,
        "punishment_applied": rec.punishment_applied,
        "punishments": [dataclasses.asdict(p) for p in rec.punishments],
        "balances_after_punishment": rec.balances_after_punishment,
    }


def _build_summary(
    run: RunConfig, game_id: str, game_seed: int, game: Game, logger: GameLogger
) -> Dict[str, object]:
    scores = game.scores()
    return {
        "run_name": run.name,
        "game_id": game_id,
        "seed": game_seed,
        "completed_at": now_iso(),
        "horizon_played": game.total_rounds,
        "final_balances": {s: game.balances[s] for s in game.seats},
        "scores": scores,
        "total_tokens": sum(game.balances.values()),
    }


def _load_summary(logger: GameLogger) -> Dict[str, object]:
    import json

    with open(logger.summary_path, "r", encoding="utf-8") as fh:
        return json.load(fh)


# --------------------------------------------------------------------------- #
# Batch
# --------------------------------------------------------------------------- #
def run_batch(
    run: RunConfig,
    run_dir: str,
    agent_kind: str = "mock",
    games: Optional[int] = None,
    client: Optional[LLMClient] = None,
    game_workers: int = 1,
    phase_workers: int = 1,
    resume: bool = False,
    on_event: Optional[Callable[[str, Dict[str, object]], None]] = None,
) -> List[Dict[str, object]]:
    """Run ``games`` games with seeds base_seed + k, writing to ``run_dir``."""
    os.makedirs(run_dir, exist_ok=True)
    n_games = games if games is not None else run.games

    tasks: List[Tuple[str, int]] = []
    for k in range(n_games):
        game_id = f"game_{k:04d}"
        game_seed = run.seed + k
        logger = GameLogger(run_dir, game_id)
        if resume and logger.is_complete():
            continue
        tasks.append((game_id, game_seed))

    summaries: List[Dict[str, object]] = []

    def _one(task):
        gid, gseed = task
        return run_game(
            run, gid, gseed, run_dir, agent_kind, client, phase_workers, on_event
        )

    if game_workers <= 1 or agent_kind == "mock":
        for t in tasks:
            summaries.append(_one(t))
    else:
        with concurrent.futures.ThreadPoolExecutor(max_workers=game_workers) as ex:
            for s in ex.map(_one, tasks):
                summaries.append(s)

    # also collect already-complete games when resuming
    if resume:
        for k in range(n_games):
            gid = f"game_{k:04d}"
            logger = GameLogger(run_dir, gid)
            if logger.is_complete() and all(s["game_id"] != gid for s in summaries):
                summaries.append(_load_summary(logger))
    return summaries


def count_calls(run: RunConfig, games: Optional[int] = None) -> Dict[str, int]:
    """Dry-run call estimate: games x rounds x players x phases."""
    n_games = games if games is not None else run.games
    cfg = run.game
    rounds = (
        cfg.horizon.rounds if cfg.horizon.mode == "fixed" else cfg.horizon.max_rounds
    )
    phases = 1  # contribute always
    if cfg.messages_enabled:
        phases += 1
    if cfg.punishment_enabled:
        phases += 1
    base = n_games * rounds * cfg.n_players * phases
    probe = n_games * rounds * cfg.n_players if cfg.intent_probe else 0
    return {
        "games": n_games,
        "rounds_per_game": rounds,
        "players": cfg.n_players,
        "phases_per_round": phases,
        "action_calls": base,
        "intent_probe_calls": probe,
        "total_calls": base + probe,
        "note": "upper bound; geometric horizon uses max_rounds; excludes retries",
    }
