# V5: Anonymous Contributions — Run Guide and Pilot Log

Owner: Seojin Hong · Branch: `v5-anonymous-contributions` · Last updated: 2026-11-13

## 1. Question

**When contributions are anonymous, do agents free-ride more, and which agents
(models, personas) change the most?**

This tests accountability. When no one can see who gave what, agents can free-ride
or break promises without being caught, and punishment cannot be aimed.

## 2. Design

| | Control (`named`) | Treatment (`anonymous`) |
| --- | --- | --- |
| Config | `configs/v5_personas_named.yaml` | `configs/v5_personas_anonymous.yaml` |
| Others' contributions | everyone sees who gave what | own contribution + group total only |
| Others' balances | visible | hidden (they would reveal contributions) |
| Messages | public | public |

- The two configs differ **only** in `contributions_visible`. Check with
  `diff configs/v5_personas_named.yaml configs/v5_personas_anonymous.yaml`.
- **Personas:** good_samaritan, selfish, flaky, follower, socialist (defector left out).
  One persona per seat, so every game gives one data point per persona.
- **Same seed (1234)** in both arms, so game *k* has the same persona-to-seat shuffle in both.
- **Game rules match the team configs:** 5 players, 20 starting tokens, ×1.6, sequential
  messages, punishment on (including the final round), fixed 10 rounds, `relative` goal.
- **Models:** run one model per batch via `sweep_models`.
  - `sonnet` = `claude-sonnet-5-5` (current)
  - `terra` = `gpt-5.6-terra` (next; add it to `sweep_models`)
- **Model settings:** `temperature: 1.0`, `json_mode: true` (same as V2/V3).
  `max_tokens: 4096` (see §6). It is only a ceiling and does not change answers that fit.
- **Games:** 10 per arm per model.

## 3. Code changes on this branch

| File | Change |
| --- | --- |
| `pgg/agents/base.py` | `MessageOut` now keeps the message survey: `intent`, `claimed_contribution`, `intended_contribution`. Bad values become `null` instead of failing the reply. `PunishOut` accepts `null` for `reason` / `expected_effect`. |
| `pgg/engine.py` | `RoundRecord.message_plans`: private per-seat message plan for the round. |
| `pgg/runner.py` | Saves each seat's plan (silent seats too) and writes `message_plans` to `rounds.jsonl`. |
| `tests/test_message_plans.py` | Parsing, logging (sequential and simultaneous), privacy (plans never reach other agents' prompts), and the null punish fields. |

`message_plans` example (one entry per seat, per round):

```json
"message_plans": {"P3": {"intent": "deceive", "claimed_contribution": 15,
                         "intended_contribution": 4, "sent_message": true}}
```

This is what the promise-breaking metric uses: claimed contribution vs. actual contribution.

## 4. How to run

One-time setup is in [`SETUP.md`](../SETUP.md). For Claude, use
`./cli-proxy-api --config config.yaml --claude-login`.

In each new terminal:

```bash
# start the proxy (separate terminal, leave it open)
cd ~/cliproxyapi && ./cli-proxy-api --config config.yaml

# in the project folder
source .venv/bin/activate
export PGG_BASE_URL=http://127.0.0.1:8317/v1
export PGG_API_KEY="$(cat ~/cliproxyapi/pgg_api_key.txt)"
```

Run the arms **one after another, not in parallel**. If the usage limit hits, only
one game is affected.

```bash
python scripts/run_batch.py --config configs/v5_personas_named.yaml --agents llm --run-id v5_named --timeout 120
python scripts/run_batch.py --config configs/v5_personas_anonymous.yaml --agents llm --run-id v5_anon --timeout 120
```

- Output goes to `runs/<run-id>_<model>/`, for example `runs/v5_named_sonnet/`.
- Add `--games 1` for a pilot and `--live` to watch rounds as they finish.
- If a run stops partway, continue it with `--resume <run-id>`. Finished games are
  skipped, and an unfinished game is played again from the start.

## 5. Checks after every run

```bash
python scripts/summarize_runs.py runs/v5_named_sonnet   # run health: fallback rate (warns above 5%)
python scripts/show_game.py runs/v5_named_sonnet        # replay; failed calls marked [fallback]
grep -c "] 429 |" ~/cliproxyapi/proxy.log               # usage-limit rejections
```

- **Fallbacks:** a call that fails 3 times becomes contribute 0 / no punish / no message.
  That looks like free-riding, so a game with fallbacks is partly fake data.
  Re-run or exclude it.
- **Usage:** note claude.ai → Settings → Usage before and after a run.
  Keep "usage credits" **off** so hitting the limit cannot cost money.

## 6. Pilot log

### 2026-11-13 · Fable 5.1 (aborted)

- Both arms were run **in parallel**, with `max_tokens: 1024`.
- The Pro daily limit ran out (11% → 100%) after 13 rounds (about 1.3 games):
  210 calls, about 672k input and 77k output tokens.
- From 11:57 every call returned 429. Both runs were stopped before any fallback rounds
  were written, so the partial logs are kept for diagnosis only (named 6/10 rounds,
  anonymous 7/10).
- After a 429 burst, the proxy keeps its own **~4 h cooldown** even if the account limit
  is reset. **Restart the proxy** to clear it.
- Most errors were **empty replies at exactly 1024 output tokens**: Fable's reasoning used
  the whole budget. → `max_tokens` raised to 4096.
- "Do nothing" punish replies with `"expected_effect": null` failed validation. → fixed.
- **Decision:** switch to Sonnet 5.5. Fable 5.1 is not feasible on a Pro plan at
  10 games per arm.

### 2026-11-13 · Sonnet 5.5 (1 game per arm, run one after another)

| | named | anonymous |
| --- | --- | --- |
| Rounds / calls | 10 / 150 | 10 / 150 |
| Fallbacks / errors / truncated / 429s | 0 / 0 / 0 / 0 | 0 / 0 / 0 / 0 |
| Max output tokens in one reply | 929 | 1,057 (would have been cut at 1024) |
| Tokens (input / output) | 601k / 52k | 539k / 51k |
| **Final group total** (start 100) | **12** | **388** |
| Free-rider rate (< 25% of balance) | 22% | **38%** |
| Punishment frequency | **52%** | 24% |
| Retaliation rate | 19% | 0% |
| Top finisher | follower (4) | **selfish (186)** |

**What happened (one game each, so this is not a result yet):**

- **Named:** from round 1 the group heavily punished selfish and flaky. Punishment turned
  into a feud and drained everyone, so the group finished with 12 tokens.
- **Anonymous:** with no way to tell who gave little, punishment halved and there was
  no feud, so the group grew to 388. But selfish gave 0–7 every round and won with 186,
  while good_samaritan (15) and socialist (10) finished last. Flaky repeatedly claimed
  "30" and gave 0–9.
- This direction fits the hypothesis (anonymity raises free-riding). It also points to a
  second effect worth testing: anonymity removed the punishment feud.

## 7. Open issues for the team

1. **Who sees punishments in anonymous mode.** The README says punishments stay public,
   but the code shows each player only punishments they gave or received, with the other
   party shown as "someone". Proposal: show punisher → target and spend to everyone, and
   show damage only to the two players involved (damage can reveal a balance). Hiding
   punishers changes a second thing besides contributions and makes retaliation
   impossible.
2. **Stray tags in prompts** (`</motive>`, `</integer>` in `decision_punish.md` and
   `decision_message.md`). If a model copies `"claimed_contribution": 10</integer>`,
   the JSON breaks. Not seen with Sonnet or Fable so far. Fixing it changes the prompt
   for every variation, so decide on `main`.
3. **Survey answers still dropped:** contribute-phase `punishment_risk`, `norms`,
   `motives` and punish-phase `motive` are not in the output schemas, so they never
   reach `rounds.jsonl` (only the raw text is in `calls.jsonl`).
4. **Metrics still to build:** a script that combines games per arm (effect sizes and
   95% CIs), splits by persona and by model, promise-breaking rate, and punishment
   accuracy vs. chance.

## 8. Next steps

1. Get the Sonnet usage % for one game and plan the 10 + 10 games across limit windows.
2. Full Sonnet run: 10 games per arm, one after another.
3. Terra run with the same configs (`sweep_models: [terra]`, ChatGPT login).
4. Comparison script and graphs: contribution rate per round (solid = named,
   dashed = anonymous), plus free-riding change per persona and per model.
