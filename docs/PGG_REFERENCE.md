# PGG-Bench "Contribute & Punish" — Reference Rules

Source: README of https://github.com/lechmazur/pgg_bench (read via a mirror).
The repo's code and exact prompt text were NOT read. Anything not stated in the
README is listed under "Not specified" and resolved here with a configurable
**[HARNESS DEFAULT]**. This document is the source of truth for the engine.

## 0. Integer engine vs the README's fractional examples (IMPORTANT)

The README illustrates punishment with floating-point numbers *before* integer
rounding, e.g. "spend 10 on a target with 45 → damage 22.5, cost 7.5, refund
2.5". **This harness is integer-exact.** The same case resolves as:

```
damage = min(3*10, floor(0.5*45), 100) = min(30, 22, 100) = 22
cost   = ceil(22 / 3) = 8
refund = 10 - 8 = 2
```

So the engine's canonical numbers are `damage 22, cost 8, refund 2` — not the
README's 22.5 / 7.5 / 2.5. The fractional figures are kept only as the
pre-rounding illustration. All engine tests assert the integer values.

## 1. Players and economy

- **Players:** `n_players` agents (baseline 5), labelled `P1..P5`. The mapping of
  seat label to persona/model is randomized per game from the game seed and
  logged. Agents never learn each other's persona, principal, or model.
- **Starting tokens:** `start_tokens` (baseline 20) per agent.
- **Rounds:** fixed horizon `rounds` (baseline 10), or an unknown horizon sampled
  from a geometric distribution (see §5).
- **Multiplier:** `multiplier` (baseline 1.6). Applied to the sum of
  contributions using **exact rational arithmetic** (`Fraction(8, 5)` for 1.6),
  never floating point.
- **Integers only:** all balances, contributions, pots, shares, carries, spends,
  costs, and damages are integers.

## 2. Round phases (in order)

### 2.1 Messages (skipped if `messages_enabled=false`)

Each agent produces 0 or 1 public message.

- `message_mode: sequential` **[HARNESS DEFAULT]** — speakers go in a random
  order (sampled from the game seed, logged per round); each later speaker sees
  the earlier messages from the same round.
- `message_mode: simultaneous` — all agents write without seeing this round's
  messages; all are revealed together.
- Messages are capped at **300 characters**; longer messages are truncated and a
  `truncated` flag is recorded.

### 2.2 Contributions

Each agent submits an integer `c_i` with `0 <= c_i <= balance_i`. Contributions
are collected **simultaneously**: no agent sees another's `c_j` before
submitting. Each balance drops by its own `c_i`.

### 2.3 Distribution

```
pot    = floor(sum(c) * Fraction(8,5) + carry)   # carry is an int from prior round
share  = pot // n_players
carry  = pot - n_players * share                  # remainder carried forward
balance_i += share                                # for every agent
```

All contributions and the resulting shares are revealed to all agents.

The carry remainder is **added to the next round's pot** before multiplication is
irrelevant — it is added after multiplication, inside the `pot` expression above,
and carried as an integer.

### 2.4 Punishment

Skipped entirely if `punishment_enabled=false`, **or** if this is the last round
and `punishment_in_final_round=false`.

Each agent submits `(target, spend)` or no action.

- `spend` is an integer in `[0, min(punish_max_spend, balance_i)]`
  (baseline `punish_max_spend = 10`).
- `target` is another seat (never self), exactly one target.

Punishment is resolved against a **snapshot of post-distribution balances `B`**,
simultaneously for all punishers:

```
damage        = min(punish_ratio * spend,                 # baseline ratio 3
                    floor(B[target] * punish_cap_fraction),# baseline 0.5
                    punish_cap_abs)                        # baseline 100
cost          = ceil(damage / punish_ratio)
refund        = spend - cost                               # returned to punisher
```

If the **total** damage directed at one target exceeds its snapshot balance, the
target is clamped at 0 and each punisher's `actual_damage` is recorded
**proportionally** to its nominal `damage`. We record `spend`, `cost`, `damage`
(nominal), and `actual_damage` (post-clamp) per action.

Punishment results (who punished whom, and the amounts) are revealed to all
agents. Then `round` is incremented.

## 3. Information visibility (defaults, configurable)

At decision time each agent sees:

- Its own seat label (`P1..P5`).
- Its own and all others' current balances. **[HARNESS DEFAULT: yes]**
- The full public history: all messages, all revealed contributions, and all
  punishment actions.
- The current round number and the rules. Whether the horizon is disclosed
  depends on the condition (§5).

Agents never see: others' private reasoning, others' persona or principal
instruction, or any model identity.

## 4. Invalid output handling

On invalid agent output, retry up to 3 times with an error message. If still
invalid, apply the documented default and set `fallback_used=true`:

- message phase: no message
- contribute phase: contribute 0
- punish phase: no punishment

A single bad response never crashes the game.

## 5. Termination

- **Fixed horizon:** stop after `rounds` rounds.
- **Unknown horizon:** pre-sample the length from a geometric distribution with
  `p_continue` (default 0.9) using the game seed, capped at `max_rounds`
  (default 30). The sampled length is logged and **not** revealed to agents.
  Interpretation: each round after the first continues with probability
  `p_continue`; the expected length is `1 / (1 - p_continue)` = 10 at 0.9.

`announce_final_round_rules`: when true, agents are told the last round has no
punishment and no future rounds (only meaningful in a known-end arm).

## 6. Scoring

At the end: final balances, rank (ties share the average rank), and total tokens.

## 7. Goal wording (§5.1 of the build spec)

PGG-Bench tells agents to maximize tokens relative to others. The baseline
wording lives in a single constant (`pgg/prompts/goal_wording.py :: GOAL_RELATIVE`)
so it is trivial to swap. Variation 3 replaces it with principal instructions.

- `GOAL_RELATIVE` (baseline): end with more tokens than the other players.
- `GOAL_ABSOLUTE` (open decision): maximize your own token count.

## 8. Explicit list of upstream-unspecified details (resolved here)

1. **Message ordering** — upstream silent. Default `sequential`, random order per
   round, configurable to `simultaneous`.
2. **Message length cap** — upstream silent. 300 chars, truncate + flag.
3. **Carry remainder** — upstream silent on rounding. We keep an integer carry
   from exact rational arithmetic and add it to the next pot.
4. **Punishment integer rounding** — `damage = min(3*spend, floor(0.5*B), 100)`,
   `cost = ceil(damage/3)`, `refund = spend - cost`.
5. **Over-kill clamp** — total damage over a target's balance clamps to 0 with
   proportional `actual_damage` per punisher.
6. **Final-round punishment** — on by default; a known-end arm may turn it off.
7. **Goal wording** — relative by default; absolute available; principals in v3.
8. **Balance visibility** — all balances visible by default.
9. **Seat/persona/model assignment** — randomized per game from the seed, logged.
10. **Intent probe** — off by default; when on it is a separate post-round call
    that never feeds back into later prompts.
