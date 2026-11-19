# V5: Anonymous Contributions — Results

Owner: Seojin Hong · Branch: `v5-anonymous-contributions` · Last updated: 2026-11-18

**Per-game data (80 games, one row per game):** [`V5_per_game_stats.csv`](V5_per_game_stats.csv),
made with `python scripts/v5_per_game_csv.py docs/V5_per_game_stats.csv` (needs the raw
`runs/` logs, which are gitignored).

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

## 2026-11-14 – 17 · Main run: Sonnet 5.5 and GPT Luna-6, 10 games per arm

Run folders (gitignored): `runs/v5_<arm>_sonnet` and `runs/v5_<arm>_chatgpt` for arm in
`named`, `anon_private`, `anon_public`, `anon_hidden`, games `game_0000`–`game_0009`.
Game k uses seed 1234 + k in every arm and model, so the persona-to-seat mapping is the same
everywhere (paired design). Sonnet ran on a Claude Pro account; GPT (`gpt-6-luna`, the V2
model, key `chatgpt` in the configs) ran on a ChatGPT Edu account. Games were run one at a
time with `scripts/run_batch.py --resume` and a watcher that stops the batch at the first 429.
For the GPT run, `sweep_models` was set to `[chatgpt]` in a copy of each config; nothing else
changed.

**Run health:** 80/80 games finished all 10 rounds. Fallbacks 0. No 429s. Calls that needed
a retry: 0–4 per game, all fixed by one retry (mostly a missing closing quote in the punish
`reason`). Longest reply: Sonnet 1,533 tokens, GPT 664. Tokens per game: Sonnet 527k–638k
input / 46k–61k output; GPT 297k–370k / 29k–36k. Time per game: Sonnet about 4 min, GPT
about 7 min. **Claude Pro usage:** about 13% of a 5-hour session and about 2% of the weekly
limit per Sonnet game.

**Visibility check (Sonnet main run, 4 games per arm):** in A and C no prompt ever showed a
punishment between two other players (A showed the punisher as "someone"; C showed only the
viewer's own punishments). In Named and B every prompt showed all punishments.

Definitions: free-riding round = gave less than 25% of balance; punishment frequency = share
of player-rounds with a punishment; retaliation rate = how often a player punished in round
t punishes its punisher in round t+1. Mean ± SD over 10 games.

### Group results

| Model | Arm | Free-rider rate | Punishment frequency | Retaliation rate | Final group total (start 100) |
| --- | --- | --- | --- | --- | --- |
| Sonnet | Named | **12% ± 3** | **46% ± 4** | 18% ± 9 | **52 ± 32** |
| Sonnet | A private | 35% ± 3 | 28% ± 5 | 14% ± 12 | 263 ± 73 |
| Sonnet | B public | 34% ± 5 | 29% ± 6 | 28% ± 10 | 207 ± 76 |
| Sonnet | C hidden | 35% ± 5 | 29% ± 5 | 15% ± 7 | 217 ± 67 |
| GPT | Named | **15% ± 6** | **55% ± 3** | 26% ± 12 | **50 ± 42** |
| GPT | A private | 33% ± 6 | 25% ± 5 | 10% ± 9 | 403 ± 75 |
| GPT | B public | 30% ± 5 | 40% ± 3 | **65% ± 10** | 341 ± 97 |
| GPT | C hidden | 29% ± 3 | 27% ± 7 | 9% ± 11 | 354 ± 104 |

Every anonymous game had more free-riding than every Named game (Sonnet: Named max 18%,
anonymous min 28%; GPT: 22% vs. 24%).

### Who free-rides: contribution rate (share of balance) / free-riding rounds, per persona

| Model | Arm | good_samaritan | socialist | follower | flaky | selfish |
| --- | --- | --- | --- | --- | --- | --- |
| Sonnet | Named | 0.95 / 0% | 0.73 / 0% | 0.55 / 1% | 0.40 / 27% | 0.30 / 35% |
| Sonnet | A private | 0.99 / 0% | 0.79 / 0% | 0.40 / 14% | 0.25 / 61% | **0.00 / 100%** |
| Sonnet | B public | 1.00 / 0% | 0.76 / 0% | 0.38 / 16% | 0.29 / 57% | **0.00 / 100%** |
| Sonnet | C hidden | 0.99 / 0% | 0.75 / 0% | 0.37 / 20% | 0.35 / 53% | **0.00 / 100%** |
| GPT | Named | 0.97 / 0% | 0.64 / 3% | 0.48 / 6% | 0.49 / 18% | 0.26 / 53% |
| GPT | A private | 1.00 / 0% | 0.72 / 0% | 0.34 / 23% | 0.27 / 44% | **0.02 / 98%** |
| GPT | B public | 0.99 / 0% | 0.68 / 1% | 0.35 / 16% | 0.33 / 34% | **0.01 / 99%** |
| GPT | C hidden | 1.00 / 0% | 0.74 / 0% | 0.39 / 17% | 0.40 / 29% | **0.00 / 100%** |

### Final tokens per persona (mean over 10 games)

| Model | Arm | selfish | flaky | follower | good_samaritan | socialist |
| --- | --- | --- | --- | --- | --- | --- |
| Sonnet | Named | **8** | 13 | 11 | 12 | 8 |
| Sonnet | A private | **153** | 50 | 36 | 14 | 11 |
| Sonnet | B public | **134** | 26 | 30 | 10 | 8 |
| Sonnet | C hidden | **140** | 28 | 34 | 9 | 6 |
| GPT | Named | **7** | 11 | 12 | 11 | 9 |
| GPT | A private | **200** | 81 | 83 | 18 | 22 |
| GPT | B public | **176** | 56 | 69 | 24 | 16 |
| GPT | C hidden | **205** | 63 | 51 | 16 | 19 |

Selfish finished first in all 60 anonymous games; in Named it was first in 2/10 (Sonnet) and
1/10 (GPT).

### Broken pledges: announced vs. actual contribution

Share of message rounds where the agent announced an amount and then gave at least 3 tokens
less (from `claimed_contribution` in the message phase).

| Model | Arm | selfish | flaky | follower | socialist | good_samaritan |
| --- | --- | --- | --- | --- | --- | --- |
| Sonnet | Named | 20% | 66% | 0% | 1% | 0% |
| Sonnet | A / B / C | 97% / 100% / 100% | 75% / 79% / 73% | 1–3% | 1–3% | 0% |
| GPT | Named | 18% | 26% | 2% | 1% | 0% |
| GPT | A / B / C | 82% / 90% / 100% | 41% / 49% / 49% | 0–1% | 0–1% | 0% |

When anonymous, Sonnet's selfish agent often stopped naming an amount (27 of 90 messages in
arm A, vs. 77 of 90 in Named) and urged the others to keep contributing fully instead.

### Findings

1. **Anonymity more than doubles free-riding in both models** (12–15% → 29–35%).
2. **Who free-rides:** the self-interested personas. Named, selfish gave about 30% of its
   balance (it was punished hard). Anonymous, it gave about 0 in every arm and model and
   finished first in all 60 anonymous games. Flaky and follower also gave less.
   good_samaritan and socialist did not change, so they carried the cost.
3. **Anonymity enables broken pledges.** Selfish gave less than it announced in about 20% of
   rounds when named and 82–100% when anonymous.
4. **Anonymity also stops the punishment feud.** Punishment frequency fell from 46–55% to
   25–40%, and anonymous groups ended 4–8× richer (about 50 vs. 200–400). In Named the groups
   ended below the 100 tokens they started with.
5. **Punishment visibility (A/B/C) does not change free-riding.** It changes retaliation:
   when punishers are shown (B), GPT retaliates in 65% of chances vs. about 10% in A and C,
   and also punishes more (40% vs. 25–27%). Sonnet shows the same direction, smaller
   (28% vs. 14–15%).

**Limits:** two models, 10 games per arm, messages on only. The selfish persona is told to
look after its own tokens, so this measures how far visibility restrains instructed
self-interest.

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
