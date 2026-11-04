# PGG Harness

A Python harness that runs the PGG-Bench "Contribute & Punish" public-goods game
with LLM agents and logs everything needed for offline study (message coding,
metrics, TrueSkill in v2).

Read [`docs/PGG_REFERENCE.md`](docs/PGG_REFERENCE.md) for the exact rules and the
list of upstream-unspecified details this harness resolves. Personas live in
[`personas/PERSONAS.md`](personas/PERSONAS.md).

## Install

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e .            # pydantic, pyyaml, openai
pip install -e '.[dev]'     # + pytest
```

Target runtime is Python 3.11+. The code also runs on 3.9 for local testing.
The `openai` package is only needed for live LLM runs; mock runs need nothing
beyond pydantic + pyyaml.

## Run

Offline, no API key (mock agents):

```bash
python scripts/run_batch.py --config configs/baseline.yaml --agents mock --games 20
```

Mock types: `cooperate` (default), `defect`, `titfortat`, `random` — set with
`--mock-type`, or per seat via `agent_type` in a config.

Real run against an OpenAI-compatible proxy (CLIProxyAPI):

```bash
export PGG_BASE_URL="http://localhost:8080/v1"
export PGG_API_KEY="..."        # never logged
python scripts/run_batch.py --config configs/baseline.yaml --agents llm --games 5
```

Estimate call volume without running anything:

```bash
python scripts/run_batch.py --config configs/baseline.yaml --dry-run
```

Resume an interrupted run (finished games are skipped):

```bash
python scripts/run_batch.py --config configs/baseline.yaml --agents llm --resume <run_id>
```

Useful flags: `--game-workers N` (parallel games), `--phase-workers N` (parallel
agent calls within a phase), `--run-id NAME`, `--runs-root DIR`, `--timeout SEC`.

## Conditions

Presets in `configs/`:

| file | condition |
| --- | --- |
| `baseline.yaml` | PGG-Bench as-is: 5 seats, 10 rounds, messages + punishment |
| `v1_known_end.yaml` | fixed horizon; final-round punishment off, rule announced |
| `v1_unknown_end.yaml` | geometric horizon (p=0.9, cap 30), length hidden |
| `v2_comm_on.yaml` / `v2_comm_off.yaml` | messaging on / off |
| `v3_uniform_max.yaml` / `v3_uniform_fair.yaml` / `v3_mixed.yaml` | principal instructions (2 max + 3 fair in mixed) |
| `personas_five.yaml` | five distinct personas, one per seat |

Seat-to-persona and seat-to-model assignment is randomized per game from the
seed and recorded in `config.json`. A condition is repeated `games` times with
seeds `seed + k`.

## Layout

```
pgg/
  config.py        pydantic schemas (GameConfig, AgentSeatConfig, ModelConfig, RunConfig)
  engine.py        pure, deterministic game logic (no I/O, no LLM)
  agents/          base interface, llm_agent (prompts+parse+retry), mock_agents
  llm/client.py    OpenAI-compatible client: retries, timeouts, usage logging
  prompts/         templates + goal-wording constants + persona loader/builder
  runner.py        run one game / a batch / resume; seat assignment; concurrency
  logging_.py      append-only JSONL writers (flush per round for resume)
  metrics.py       per-game metrics from the logs
configs/           yaml presets
tests/             engine math, privacy, mocks, determinism, personas, dry-run
scripts/run_batch.py
```

## Logs (`runs/<run_id>/<game_id>/`)

- `config.json` — resolved config, seed, git hash, model names, seat assignment,
  sampled horizon, timestamps.
- `rounds.jsonl` — one line per round: speaker order, messages, balances before
  and after each phase, contributions, pot/share/carry, punishment actions with
  `spend`/`cost`/`damage`/`actual_damage`, and `fallback_used` flags.
- `calls.jsonl` — one line per LLM call: seat, phase, round, full prompt
  messages, raw response, parsed output, latency, token usage, retries, errors.
  (Mock runs make no LLM calls, so this file is absent.)
- `summary.json` — final balances, ranks, totals, horizon played, per-game
  metrics.

Writes are append-only and flushed per round, so a crashed run resumes at the
last complete round. API keys are never written. With mock agents, the same seed
reproduces `rounds.jsonl` byte-for-byte across processes.

## Determinism

The engine is pure and integer-exact (the 1.6 multiplier is applied as
`Fraction(8, 5)`, never floating point). All randomness is seeded with a stable
hash of the game seed plus a label, so logs reproduce across processes regardless
of `PYTHONHASHSEED`. LLM sampling is not deterministic; only the engine and mock
agents are.

## Metrics

`pgg/metrics.py` computes, per game: contribution by round (absolute and fraction
of balance), free-rider rate (zero and below-threshold), punishment frequency and
spend fraction by round, damage-received fraction, punishment-target tagging
(low/high contributor, leader, antisocial), retaliation rate, endgame drop, and
final tokens/rank/average-partner-tokens. The unit of analysis is the game.

## Tests

```bash
pytest -q
```

## Not in v1

TrueSkill leaderboard, plots, and automated message coding (the logs support
them). No training or fine-tuning.
