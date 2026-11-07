# thePPGExperiment: PGG Harness

Five AI agents play the PGG-Bench "Contribute & Punish" public-goods game. The
harness records every message, contribution and punishment so the games can be
analyzed later.

- Game rules and the details this harness had to decide: [`docs/PGG_REFERENCE.md`](docs/PGG_REFERENCE.md)
- How the files connect (diagram): [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)
- **Setting up a new computer, including the model proxy: [`SETUP.md`](SETUP.md)**
- Personas: [`personas/defs/`](personas/defs/), one file per persona

## Install

Requires Python 3.9 or newer and git.

```bash
git clone https://github.com/itsani-cmd/thePPGExperiment.git
cd thePPGExperiment
python3 -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install pydantic pyyaml openai pytest
```

Check the install:

```bash
python -m pytest -q                  # all tests should pass
```

On Python 3.11 or newer you can use `pip install -e '.[dev]'` instead. On
older Python that command fails because `pyproject.toml` declares 3.11.

To run games with real AI models you also need the local proxy. See
[`SETUP.md`](SETUP.md).

## Run games

### Without any AI account (mock agents)

Mock agents follow fixed rules and ignore personas. Use them to check that
everything runs.

```bash
python scripts/run_batch.py --config configs/baseline.yaml --agents mock --games 2 --live
```

Mock types, set with `--mock-type`: `cooperate` (default), `defect`,
`titfortat`, `random`.

### With real AI agents

Start the proxy first (see [`SETUP.md`](SETUP.md)), then in the project
terminal:

```bash
source .venv/bin/activate
export PGG_BASE_URL=http://127.0.0.1:8317/v1
export PGG_API_KEY="$(cat ~/cliproxyapi/pgg_api_key.txt)"

# 2-round test, about 30 model calls, about 1 minute
python scripts/run_batch.py --config configs/smoke_chatgpt.yaml --agents llm --live

# full 10-round game with the five personas, about 150 calls
python scripts/run_batch.py --config configs/local_chatgpt.yaml --agents llm --live
```

### Command options

| option | what it does |
| --- | --- |
| `--config FILE` | which experiment to run (required) |
| `--agents mock` or `llm` | fake agents or real models |
| `--games N` | number of games (overrides `games:` in the config) |
| `--live` | print each round on screen as it finishes |
| `--dry-run` | print how many model calls the run would make, then exit |
| `--run-id NAME` | name of the output folder under `runs/` (default: config name + timestamp) |
| `--resume NAME` | continue an interrupted run; finished games are skipped |
| `--mock-type TYPE` | behavior of mock agents |
| `--phase-workers N` | parallel agent calls within a phase (default 5) |
| `--game-workers N` | games run in parallel (default 1) |
| `--timeout SEC` | time limit per model call (default 60) |

Always run `--dry-run` before a large batch. A full game is about 150 calls,
so 20 games is about 3,000.

Reusing a `--run-id` that already has a finished game returns the saved result
instead of playing again. Use a new name, or leave `--run-id` out.

## Watch and check games

**Live:** add `--live` to see each round as it finishes: messages,
contributions, the pot and share, who punished whom and why, and balances.
Each round with real models takes about 30 seconds.

**Replay a saved game:**

```bash
python scripts/show_game.py                         # most recent game
python scripts/show_game.py runs/<run_id>/game_0000 # one game
python scripts/show_game.py runs/<run_id>           # every game in a run
```

**Raw logs**, in `runs/<run_id>/<game_id>/`:

| file | contents |
| --- | --- |
| `config.json` | full settings, seed, which persona and model each seat got, number of rounds played |
| `rounds.jsonl` | one line per round: messages, balances before and after each phase, contributions, pot, share, carry, every punishment with spend/cost/damage, and `fallback_used` flags |
| `calls.jsonl` | one line per model call: full prompt, raw reply, parsed answer, time taken, token usage, retries, errors (real-model runs only) |
| `summary.json` | final balances, ranks, totals, and all metrics |

**Check for failed calls.** If a model call fails three times, the agent falls
back to a safe default (contribute 0, no punishment, no message) and
`fallback_used` is set to true. `show_game.py` marks these with `[fallback]`.
A game with many fallbacks has partly fake data.

## Variations already set up

All files are in `configs/`.

| file | variation | what is set |
| --- | --- | --- |
| `baseline.yaml` | PGG-Bench as is | 5 seats, no personas, 10 rounds, messages and punishment on |
| `personas_five.yaml` | five personas | one persona per seat from `personas/defs/`, shuffled each game |
| `smoke_chatgpt.yaml` | quick test | five personas, 2 rounds, ChatGPT |
| `local_chatgpt.yaml` | full test | five personas, 10 rounds, ChatGPT |
| `v1_known_end.yaml` | V1: known end | told "exactly 10 rounds"; no punishment in the last round, and agents are told that |
| `v1_unknown_end.yaml` | V1: unknown end | length drawn at random (90% chance to continue each round, at most 30); length hidden |
| `v2_comm_on.yaml` | V2: messages on | same as baseline |
| `v2_comm_off.yaml` | V2: messages off | `messages_enabled: false` |
| `v3_uniform_max.yaml` | V3: all "maximize" | every seat gets the `principal_selfish` instruction only |
| `v3_uniform_fair.yaml` | V3: all "fair" | every seat gets the `principal_socialist` instruction only |
| `v3_mixed.yaml` | V3: mixed | 2 maximize + 3 fair, seats shuffled each game |
| `v4_reward_only.yaml` | V4: rewards instead of punishment | `punishment_enabled: false`, `reward_enabled: true`; compare with `baseline.yaml` |
| `v4_reward_and_punish.yaml` | V4: both | reward phase, then punishment phase |
| `v5_anonymous.yaml` | V5: anonymous contributions | each player sees only their own gift and the group total; other balances hidden |
| `v6_planted_defector.yaml` | V6: planted defector | 4 plain seats + 1 seat with the `defector` persona (told to never contribute) |
| `v7_exit.yaml` | V7: exit option | players may sit a round out for `exit_payoff: 4` |

**Before running these with real models:**

1. **Change the model name.** Every file except `smoke_chatgpt.yaml` and
   `local_chatgpt.yaml` still uses the placeholder `gpt-4o-mini`. Set `model:`
   to a name your proxy serves (for example `gpt-6-luna`), or the run stops at
   startup with "configured models not served".
2. **V1:** the two arms differ in two ways. The known-end file also turns off
   last-round punishment. For a clean comparison, add a known-end copy with
   `punishment_in_final_round: true`. The unknown-end text shown to agents does
   not mention 90%; that wording is in `horizon_text()` in
   `pgg/prompts/builder.py`.
3. **V3:** the principal texts are the two blocks at the bottom of
   `personas/PERSONAS.md`. Every agent also gets the base goal "finish with more
   tokens than the other players", which may conflict with the "fair"
   instruction.

## Making a new variation

Copy a file in `configs/`, rename it, change the values, and run it with
`--config`. No code changes are needed for anything in the tables below.

### Game settings (under `game:`)

| setting | default | meaning |
| --- | --- | --- |
| `n_players` | 5 | number of agents; `seats:` must have this many entries |
| `start_tokens` | 20 | tokens each agent starts with |
| `multiplier` | 1.6 | the fund is multiplied by this before being shared |
| `horizon` | `{mode: fixed, rounds: 10}` | game length; or `{mode: geometric, p_continue: 0.9, max_rounds: 30}` for a random, hidden length |
| `messages_enabled` | true | public messages each round |
| `message_mode` | sequential | `sequential` (later speakers see earlier messages) or `simultaneous` |
| `message_max_chars` | 300 | longer messages are cut and flagged |
| `punishment_enabled` | true | punishment phase each round |
| `punish_max_spend` | 10 | most tokens an agent can spend punishing per round |
| `punish_ratio` | 3 | tokens removed from the target per token spent |
| `punish_cap_fraction` | 0.5 | damage capped at this share of the target's balance |
| `punish_cap_abs` | 100 | absolute damage cap |
| `punishment_in_final_round` | true | whether the last round has punishment |
| `reward_enabled` | false | reward phase each round, after distribution and before punishment: spend tokens to give tokens to one other player |
| `reward_max_spend` | 10 | most tokens an agent can spend rewarding per round |
| `reward_ratio` | 1 | tokens the receiver gets per token spent (1 = a pure transfer; above 1 creates tokens) |
| `exit_enabled` | false | in the contribution phase a player may exit the round |
| `exit_payoff` | 1 | extra tokens an exiter gets (paid from outside the game). An exiter keeps their balance, contributes nothing, gets no share, and cannot punish, reward or be punished or rewarded. If anyone exits, the fund is split among the others (if everyone exits it carries over) |
| `contributions_visible` | named | `anonymous`: each player sees only their own contribution and the group total, and other balances are hidden regardless of `show_all_balances`. Messages, punishments, rewards and exits stay public |
| `announce_final_round_rules` | true | tell agents when they are in the last round |
| `goal_wording` | relative | `relative` ("finish ahead of others") or `absolute` ("maximize your own tokens") |
| `show_all_balances` | true | agents see everyone's balance, or only their own |
| `intent_probe` | false | extra private question after each round: predict others' next contribution and rank how deceptive they are; never shown to other agents |
| `free_rider_fraction_threshold` | 0.25 | metrics only: contributing less than this share of balance counts as free-riding |

### Seats (under `seats:`)

One entry per player:

```yaml
seats:
  - {persona: selfish, principal: selfish, model: chatgpt}
```

- `persona`: gives the seat that persona's behavior description (`disposition`), or `null` for none.
- `principal`: gives the seat that persona's principal instruction, or `null`. V3 sets only this.
- `model`: a key from the `models:` section.
- `agent_type`: mock agent type for this seat (mock runs only): `cooperate`, `defect`, `titfortat`,
  `random` or `leaver` (always exits).

Seats are shuffled onto P1 to P5 each game, and the mapping is saved in
`config.json`.

### Models (under `models:`)

```yaml
models:
  chatgpt:
    model: gpt-6-luna      # must be a name the proxy lists at /v1/models
    temperature: 1.0
    max_tokens: 400
    json_mode: true        # set false if the model rejects JSON mode
    reasoning: null        # reasoning effort, if the model supports it
```

Give seats different keys to put different models in one game. The `base_url`
field is currently ignored; the address always comes from `PGG_BASE_URL`.

### Run settings (top level)

| setting | meaning |
| --- | --- |
| `name` | label used in output folder names |
| `games` | number of games; game *k* uses seed `seed + k` |
| `seed` | base random seed |
| `personas_file` | `personas/defs` (one file per persona) or `personas/PERSONAS.md` |

### Things that need more than a config file

- **New persona:** add `personas/defs/<name>.md`, then use `<name>` in `seats:`.
- **Different text sent to agents:** edit `pgg/prompts/system_base.md` or the
  `decision_*.md` files. These are shared by every variation.
- **New game rule:** code changes in `pgg/engine.py` and `pgg/runner.py`.
- **New measurement:** code in `pgg/metrics.py`.

## Metrics

Each game's `summary.json` includes: contribution by round (tokens and share of
balance), free-rider rate, punishment frequency and spending by round, damage
received, punishment targets (low contributor, high contributor, leader;
punishing a high contributor counts as antisocial), retaliation rate, endgame
drop (last-round contribution minus the average of the middle rounds), and final
tokens, rank and average partner tokens. Each game is one data point; there is no
script yet that combines games.

## Project layout

```
pgg/
  config.py         settings schema and YAML loading
  engine.py         game rules; no AI, no files
  runner.py         runs games: assigns seats, asks agents, writes logs
  agents/           mock agents and the AI agent (prompts, parsing, retries)
  llm/client.py     calls the model API
  prompts/          text sent to agents, persona loading
  transcript.py     readable output for --live and show_game.py
  logging_.py       writes the log files
  metrics.py        per-game statistics
configs/            one YAML file per experiment
personas/defs/      one file per persona
scripts/
  run_batch.py      run games
  show_game.py      replay a game
tests/              rule and logging tests
docs/               rules reference and architecture diagram
```

## Determinism

Game rules use whole numbers only; the 1.6 multiplier is applied as the exact
fraction 8/5. With mock agents the same seed gives identical `rounds.jsonl`
files on any computer. Real models give different answers each run.

## Not built yet

TrueSkill leaderboard, plots, automated message coding, and a script that
combines results across games. The logs contain what these need.
