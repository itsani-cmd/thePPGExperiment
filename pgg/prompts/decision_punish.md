It is round {round} of the game. This is the PUNISHMENT phase.

{state_block}

{distribution_block}

You may spend tokens to punish exactly one other player, or do nothing. If you punish, spend is an integer from 1 to {max_spend} (and no more than your balance {own_balance}). Spending X costs you X tokens and reduces the target by up to 3X, capped at 50% of the target's current balance (and at most 100); if the cap lowers the damage, part of your spend is refunded. You cannot punish yourself.

Reply with ONLY one of these JSON objects:
- To punish:   {{"target": "<seat label, e.g. P3>", "spend": <integer 1..{max_spend}>, "reason": "<short rationale>", "expected_effect": "<what you expect to happen>"}}
- To do nothing: {{"target": null, "spend": 0, "reason": "<short rationale>"}}
