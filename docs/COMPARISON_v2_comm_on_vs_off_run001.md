# Comparison: communication ON vs OFF (`v2_comm_on_run001` vs `v2_comm_off_run001`)

**Design.** Same seed, same five persona seats, same two models (`gpt-6-luna` as `chatgpt`, `claude-sonnet-5-5` as
`claude`), 10 rounds, punishment ON. The only intended difference is the message phase. The seed gives the same seat
mapping in all four games (P1 `good_samaritan`, P2 `follower`, P3 `selfish`, P4 `socialist`, P5 `flaky`), so the games
are matched. Single-condition reports: `docs/FINDINGS_v2_comm_on_run001.md` and `docs/FINDINGS_v2_comm_off_run001.md`.

**Read this first.** There is one game per cell (2 conditions x 2 models = 4 games). That is enough to see what the
data looks like and to form hypotheses, not to say communication caused anything. Where a number goes the opposite way
in the two models, treat it as noise. Section 5 lists the ones that did.

## 1. Side by side

| | on, chatgpt | off, chatgpt | on, claude | off, claude |
|---|---|---|---|---|
| Calls / LLM tokens | 151 / 396k | 100 / 175k | 151 / 675k | 100 / 256k |
| Mean contribution | 0.53 | 0.67 | 0.52 | 0.65 |
| Final total (of 100) | 15 | 28 | 32 | 42 |
| Tokens destroyed by punishment | 279 | 268 | 296 | 364 |
| Punishment actions (tokens spent) | 29 (75) | 30 (82) | 22 (76) | 28 (97) |
| Efficiency | -0.008 | -0.007 | -0.006 | -0.005 |
| Final Gini | 0.32 | 0.14 | 0.075 | 0.28 |
| Cooperation slope | +0.005 | +0.024 | +0.005 | +0.001 |
| Settles at round | none | none | none | 5 |
| Punishments aimed at the selfish seat | 12 of 29 | 13 of 30 | 8 of 22 | 16 of 28 |
| Next-round change if punished | +0.04 | +0.26 | +0.29 | +0.10 |

## 2. What goes the same way in both models

1. **Higher contributions without messages.** Mean contribution is +0.14 (chatgpt) and +0.13 (claude) higher
   with communication off. The final group total is also higher (28 vs 15, and 42 vs 32).
2. **Cost savings.** Without the message phase a game takes 100 calls instead of 151, and 56% (chatgpt) and 62%
   (claude) fewer LLM tokens.
3. **The selfish seat does worse without messages.** It finishes first (chatgpt) or tied for second (claude) with
   communication on, and last in both games with it off:

   | Selfish final tokens (rank) | on | off |
   |---|---|---|
   | chatgpt | 5 (1st) | 3 (5th) |
   | claude | 7 (tied 2nd) | 0 (5th) |

4. **Wealth is still mostly destroyed.** Efficiency is about zero in all four games, and punishment destroys 268 to
   364 tokens of the 100 that are put in.
5. **Persona order holds.** good_samaritan has the highest and selfish the lowest contribution in all four games.
   The exact middle order (socialist > follower > flaky) holds in three of the four. The chatgpt comms-off game has them within
   0.01 of each other.

## 3. Where the reasons differ

Counts are from rough regex matching on the saved `reason` field of contribution and punishment decisions, so treat
them as indicative.

| Reasons citing... | on, chatgpt | off, chatgpt | on, claude | off, claude |
|---|---|---|---|---|
| a promise or announced amount ("I said I would...") | 29 of 79 | 0 of 80 | 39 of 72 | 0 of 78 |
| observed history (last round's average, who punished whom) | 8 of 79 | 19 of 80 | 23 of 72 | 28 of 78 |
| the principal's brief | 0 | 0 | 7 of 72 | 12 of 78 |

- **Commitment language disappears, history language replaces it.** With messages, 37 to 54% of reasons lean on
  something the agent said earlier. Without messages that is zero, and reasons use the visible record.
- **Messages cushion the selfish seat.** With messages, the selfish agent pledges a small amount, and then cites the pledge
  as protection ("Contributing the promised 5 limits punishment and reputational risk", chatgpt on R1). It opens with
  5 and 3 in the two comms-on games. Without messages it opens with 0 in both, is punished hard (claude: "lost 27 tokens"
  in round 1) and then raises its contributions for a few rounds.
- **The follower punishes more without messages.** The brief says it punishes only when most of the group is already
  punishing the same player. With communication on, it punished 1 time (chatgpt) and 0 times (claude); with it off,
  2 times and 6 times. In claude it joins every round from 5 to 10 against the selfish seat, with near-identical text.
  With no messages, punishment history is the only visible group signal.
- **Punishment concentrates on the selfish seat more in one model.** Chatgpt: 12 of 29 (on) and 13 of 30 (off), which is
  about the same. Claude: 8 of 22 (on) and 16 of 28 (off). Only claude shows the shift, so it is not yet a pattern.

## 4. Principal vs. peers, across conditions

The conclusion from the single-condition reports holds in both conditions: the agents follow their brief and respond to
how other agents treated them, and the group total suffers. The selfish seat is the test that separates "obeys the
principal" from "serves the group", and it acts on its brief in all four games.

What communication changes is **how well that works for the selfish seat**: with messages it can pledge and persuade
and ends at or near the top, and without them it is punished by several personas at once and ends last. That fits the
selfish brief's own text ("Uses messages to persuade others to contribute while giving little"), so it is
a plausible hypothesis, though one game per cell cannot confirm it.

## 5. What did not hold up (likely noise)

- **Punishment's effect on the next round flipped between conditions in both models.** Claude +0.29 (on) vs +0.10
  (off), chatgpt +0.04 (on) vs +0.26 (off). In the comms-on report I read the claude number as punishment working
  better in claude. Given this flip, that reading is not supported.
- **Gini moves in opposite directions:** chatgpt 0.32 to 0.14, claude 0.075 to 0.28.
- **Tokens destroyed:** about the same in chatgpt (279 vs 268), higher without messages in claude (296 vs 364),
  even though that game also ends with more wealth.
- **The follower's tracking correlation** is negative in three of four games despite reasons that say it follows the
  group average. It looks like a metric problem, and I haven't investigated it.
- **Cooperation slope** and the "settles at round" value come from 10 rounds in one game.
- An earlier note in chat said comms-on punishment was "spread across several players". In chatgpt that is not true: 12 of
  29 punishments already hit the selfish seat with communication on.

## 6. Suggested next steps

1. Run both configs at the full 20 games per model. That is 40 games per config, about 150 calls per game with
   communication on and 100 with it off. Then compare with `scripts/compare_models.py`.
2. Compare the selfish seat's rank across the two conditions first. It is the strongest candidate effect in this run.
3. Check how `tracks_others_corr` is computed before relying on it for the follower.
4. Decide whether punishment in round 10 should stay on (`punishment_in_final_round`), since it cannot change anyone's
   later behaviour.
5. Add a brief that conflicts with the group's interest, to separate principal-following from common-interest behaviour.
