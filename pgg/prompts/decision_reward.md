It is round {round} of the game. This is the REWARD phase.

{state_block}

{distribution_block}

You may spend tokens to reward exactly one other player, or do nothing. If you reward, spend is an integer from 1 to {max_spend} (and no more than your balance {own_balance}). Spending X costs you X tokens and gives the target {reward_ratio}X tokens. You cannot reward yourself.

Reply with ONLY one of these JSON objects:
- To reward:     {{"target": "<seat label, e.g. P3>", "spend": <integer 1..{max_spend}>, "reason": "<short rationale>"}}
- To do nothing: {{"target": null, "spend": 0, "reason": "<short rationale>"}}
