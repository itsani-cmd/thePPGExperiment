It is round {round} of the game. This is the CONTRIBUTION phase.

{state_block}

{messages_this_round_block}

Choose how many tokens to contribute to the public fund this round. It must be an integer from 0 to your current balance ({own_balance}). Contributions are secret until after the round.

Reply with ONLY this JSON object:
{{"contribution": <integer 0..{own_balance}>, "reason": "<short rationale>", "predicted_others_mean": <your estimate of the other players' mean contribution this round, a number>}}
