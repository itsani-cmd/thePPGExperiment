# V5: Anonymous Contributions — Results

Owner: Seojin Hong · Branch: `v5-anonymous-contributions` · Last updated: 2026-11-15

Configs (four arms, same seed, identical except the two visibility settings):

| Arm | Config | Contributions | Punishments |
| --- | --- | --- | --- |
| Named (control) | `v5_personas_named.yaml` | named | public |
| Anon-A | `v5_personas_anonymous.yaml` | anonymous | private (own given/received, punisher = "someone") |
| Anon-B | `v5_personas_anonymous_public.yaml` | anonymous | public |
| Anon-C | `v5_personas_anonymous_hidden.yaml` | anonymous | hidden (only the ones you gave) |

Every arm sets `punishments_visible` explicitly, so each system prompt states its punishment
rule in one sentence. Because of that sentence (and `max_tokens: 4096`), V5 Named games are
not identical to the V2 comm-on games; compare V5 arms only with each other.

## 2026-11-14 – 15 · Main run: Sonnet 5.5, 4 games per arm

Run folders (gitignored): `runs/v5_named_sonnet`, `runs/v5_anon_private_sonnet`,
`runs/v5_anon_public_sonnet`, `runs/v5_anon_hidden_sonnet`, games `game_0000`–`game_0003`.
Game k uses seed 1234 + k in every arm, so the persona-to-seat mapping is the same across arms
(paired design). Games were run one at a time, interleaved across arms, with
`scripts/run_batch.py --resume` and a watcher that stops the batch at the first 429.

**Run health:** 16/16 games finished all 10 rounds. Fallbacks 0. JSON errors 0–3 per game,
all fixed by one retry (mostly a missing closing quote in the punish `reason`). Longest reply
1,533 tokens (would have been cut at 1024). About 550k–615k input and 48k–58k output tokens
per game. **Pro plan usage:** about 13% of a 5-hour session and about 2% of the weekly limit
per game.

**Visibility check:** in A and C no prompt ever showed a punishment between two other players
(A showed the punisher as "someone"; C showed only the viewer's own punishments). In Named and
B every prompt showed all punishments.

### Group results (mean ± SD over 4 games)

| Arm | Free-rider rate (< 25% of balance) | Punishment frequency | Retaliation rate | Final group total (start 100) |
| --- | --- | --- | --- | --- |
| Named | **12% ± 2** | **44% ± 4** | 19% ± 8 | **71 ± 34** |
| A private | 37% ± 2 | 27% ± 4 | 10% ± 9 | 270 ± 50 |
| B public | 35% ± 4 | 28% ± 7 | 25% ± 11 | 232 ± 110 |
| C hidden | 36% ± 4 | 27% ± 6 | 18% ± 5 | 232 ± 70 |

### Who free-rides: contribution rate (share of balance) / free-riding rounds, per persona

| Arm | good_samaritan | socialist | follower | flaky | selfish |
| --- | --- | --- | --- | --- | --- |
| Named | 0.89 / 0% | 0.73 / 0% | 0.56 / 0% | 0.46 / 25% | 0.30 / 37% |
| A private | 1.00 / 0% | 0.77 / 0% | 0.38 / 18% | 0.24 / 68% | **0.00 / 100%** |
| B public | 1.00 / 0% | 0.76 / 0% | 0.36 / 22% | 0.31 / 56% | **0.00 / 100%** |
| C hidden | 0.98 / 0% | 0.77 / 0% | 0.40 / 22% | 0.28 / 57% | **0.00 / 100%** |

### Final tokens per persona (mean over 4 games)

| Arm | selfish | flaky | follower | good_samaritan | socialist |
| --- | --- | --- | --- | --- | --- |
| Named | **7** | 19 | 18 | 17 | 10 |
| A private | **147** | 56 | 41 | 15 | 12 |
| B public | **144** | 35 | 34 | 10 | 10 |
| C hidden | **140** | 35 | 39 | 9 | 8 |

### Findings (early: one model, 4 games per arm)

1. **Anonymity roughly triples free-riding** (12% → 35–37%). All 12 anonymous games are
   above every Named game, and the spread is small.
2. **Who free-rides:** the self-interested personas. With names shown, selfish still gave
   about 30% of its balance (it was punished hard). Once anonymous it gave **0 in every round
   of every game**. Flaky (0.46 → 0.24–0.31) and follower (0.56 → 0.36–0.40) also gave less.
   good_samaritan and socialist did not change, so they carried the cost: selfish finished
   first in all 12 anonymous games and never first in Named.
3. **Anonymity also stops the punishment feud.** Punishment frequency fell from 44% to about
   27%, and the anonymous groups ended 3–4× richer than the Named groups (71 vs 230–270).
4. **Punishment visibility (A/B/C) did not change free-riding** (35–37% in all three). It may
   change retaliation: highest when punishers are shown (B 25%), lowest when they are shown
   as "someone" (A 10%). The spread is large, so this needs more games.

**Limits:** one model (Sonnet 5.5) and 4 games per arm. Next: more games per arm and a second
model (GPT, to match V2 use `gpt-6-luna`).

## Pilots (not counted)

The pilots below ran before `punishments_visible` existed, so their prompts did not state a
punishment rule.

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

**Plan usage (Pro):** both games together used **21%** of the daily limit, about
**10–11% per game**. So one limit window fits roughly 9 games, and the full run
(10 games per arm) needs about 2–3 windows.

**What happened (one game each, so this is not a result yet):**

- **Named:** from round 1 the group heavily punished selfish and flaky. Punishment turned
  into a feud and drained everyone, so the group finished with 12 tokens.
- **Anonymous:** with no way to tell who gave little, punishment halved and there was
  no feud, so the group grew to 388. But selfish gave 0–7 every round and won with 186,
  while good_samaritan (15) and socialist (10) finished last. Flaky repeatedly claimed
  "30" and gave 0–9.
- This direction fits the hypothesis (anonymity raises free-riding). It also points to a
  second effect worth testing: anonymity removed the punishment feud.
