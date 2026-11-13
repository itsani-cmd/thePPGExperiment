# V5: Anonymous Contributions — Pilot Results

Owner: Seojin Hong · Branch: `v5-anonymous-contributions` · Last updated: 2026-11-13

Configs: `configs/v5_personas_named.yaml` (control) and
`configs/v5_personas_anonymous.yaml` (treatment). The two files differ only in
`contributions_visible`.

## 2026-11-13 · Fable 5.1 (aborted)

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

## 2026-11-13 · Sonnet 5.5 (1 game per arm, run one after another)

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
